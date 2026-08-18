from __future__ import annotations

import math
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Protocol, cast

from inductor_designer.adapters.pyaedt.desktop_cleanup import (
    release_live_app,
    release_orphaned_desktops,
)
from inductor_designer.adapters.pyaedt.field_reader import (
    CURRENT_DENSITY_QUANTITY,
    FLUX_DENSITY_QUANTITY,
    EvaluatedArea,
    read_field_areas,
)
from inductor_designer.adapters.pyaedt.live_app import LiveAppExtraction
from inductor_designer.adapters.pyaedt.material_props import (
    apply_steinmetz_unit_fix,
    enable_core_loss,
)
from inductor_designer.adapters.pyaedt.polyline_data import polyline_data
from inductor_designer.adapters.pyaedt.result_reader import read_scalar_results
from inductor_designer.adapters.pyaedt.section_sheets import (
    create_conductor_section_sheets,
    create_core_section_sheets,
)
from inductor_designer.adapters.pyaedt.solve_watch import analyze_watched
from inductor_designer.adapters.pyaedt.stage_progress import (
    log_desktop_messages as _log_desktop_messages,
)
from inductor_designer.adapters.pyaedt.stage_progress import (
    record_cancellation as _record_cancellation,
)
from inductor_designer.application.ports.maxwell_exporter import (
    Maxwell3dExportRequest,
    Maxwell3dExportResult,
    Maxwell3dGeometryOnlyRequest,
    StageRecord,
)
from inductor_designer.geometry.primitives import PathSegment
from inductor_designer.simulation.capabilities import DcBiasStrategy
from inductor_designer.simulation.maxwell_plan import (
    COPPER_MATERIAL,
    INITIAL_MESH_SLIDER_LEVEL,
    GeometryOnlyMaxwell3dPlan,
    GeometryOnlyWindingPlan,
    Maxwell3dDesignPlan,
    WindingGroupPlan,
)
from inductor_designer.simulation.raw_results import RawScalarResults
from inductor_designer.simulation.run_control import (
    CancellationToken,
    RunCancelled,
    StagePhase,
)
from inductor_designer.simulation.run_control import (
    emit_stage_event as _emit,
)
from inductor_designer.simulation.run_control import (
    is_cancelled as _cancelled,
)


def _results_message(raw: RawScalarResults) -> str:
    if raw.diagnostics:
        return f"Result extraction incomplete: {'; '.join(raw.diagnostics)}"
    return (
        f"{len(raw.windings)} winding result(s), {len(raw.matrices)} matrix/matrices, "
        f"convergence {'read' if raw.convergence is not None else 'not exposed'}."
    )


class Maxwell3dApp(Protocol):
    modeler: Any
    mesh: Any
    post: Any
    materials: Any
    odesign: Any

    def assign_material(self, assignment: Any, material: str) -> Any: ...

    def set_core_losses(
        self, assignment: Any, core_loss_on_field: bool = ...
    ) -> Any: ...

    def assign_coil(self, assignment: Any, **kwargs: Any) -> Any: ...

    def assign_winding(self, assignment: Any = ..., **kwargs: Any) -> Any: ...

    def add_winding_coils(self, assignment: Any, coils: Any) -> Any: ...

    def eddy_effects_on(self, assignment: Any, **kwargs: Any) -> Any: ...

    def create_setup(self, name: str) -> Any: ...

    def assign_matrix(self, assignment: Any, **kwargs: Any) -> Any: ...

    def validate_simple(self, log_file: str | None = None) -> int: ...

    def analyze_setup(self, name: str, *, blocking: bool = True) -> bool: ...

    are_there_simulations_running: Any

    def stop_simulations(self, clean_stop: bool = True) -> Any: ...

    def setup_convergence(self, name: str) -> str: ...

    def solve_status(self, name: str) -> str: ...

    def solution_values(self, expressions: tuple[str, ...]) -> Any: ...

    def create_section_rectangle(
        self,
        name: str,
        azimuth_deg: float,
        r_inner_m: float,
        r_outer_m: float,
        half_height_m: float,
    ) -> str: ...

    def create_section_disc(
        self,
        name: str,
        center_m: tuple[float, float, float],
        normal: tuple[float, float, float],
        radius_m: float,
    ) -> str: ...

    def field_value(
        self,
        quantity: str,
        scalar_function: str,
        object_name: str,
        object_type: str,
    ) -> float: ...

    def convergence_rows(self, name: str) -> tuple[tuple[int, float], ...]: ...

    def save_project(self, path: str) -> bool: ...

    def release_desktop(self, close_projects: bool, close_desktop: bool) -> None: ...

    def desktop_messages(self) -> tuple[str, ...]: ...


class Maxwell3dAppFactory(Protocol):
    pyaedt_version: str

    def create(self, **kwargs: object) -> Maxwell3dApp: ...


class DefaultMaxwell3dAppFactory:
    @property
    def pyaedt_version(self) -> str:
        try:
            return version("pyaedt")
        except PackageNotFoundError:
            return "not-installed"

    def create(self, **kwargs: object) -> Maxwell3dApp:
        from ansys.aedt.core import Maxwell3d

        try:
            return cast(Maxwell3dApp, LiveAppExtraction(Maxwell3d(**kwargs)))
        except Exception:
            # See `DefaultMaxwell2dAppFactory.create`: a failed launch owns a
            # live desktop process that nothing else will close.
            release_orphaned_desktops()
            raise


def _stage_units(
    app: Maxwell3dApp,
    plan: Maxwell3dDesignPlan | GeometryOnlyMaxwell3dPlan,
) -> str:
    app.modeler.model_units = "meter"
    return "Model units set to meter."


def _stage_materials(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    spec = plan.core.material
    material = app.materials.add_material(spec.name)
    material.permeability = (
        [[h, b] for b, h in spec.bh_curve]
        if spec.bh_curve
        else spec.relative_permeability
    )
    material.conductivity = spec.conductivity_s_per_m
    if spec.mass_density_kg_per_m3 is not None:
        material.mass_density = spec.mass_density_kg_per_m3
    if spec.steinmetz is not None:
        accepted = material.set_power_ferrite_coreloss(
            cm=spec.steinmetz.k,
            x=spec.steinmetz.alpha,
            y=spec.steinmetz.beta,
        )
        if not accepted:
            raise RuntimeError("PyAEDT rejected the ferrite core-loss model.")
        apply_steinmetz_unit_fix(material, spec.steinmetz)
    return f"Material {spec.name} created (draft={spec.draft})."


def _create_core_geometry(
    app: Maxwell3dApp,
    name: str,
    profile: tuple[PathSegment, ...],
) -> None:
    data = polyline_data(profile, closed=True)
    app.modeler.create_polyline(
        points=[list(point) for point in data.points],
        segment_type=list(data.kinds),
        name=name,
        cover_surface=True,
        close_surface=False,
    )
    app.modeler.sweep_around_axis(name, axis="Z", sweep_angle=360)


def _stage_core(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    _create_core_geometry(app, plan.core.name, plan.core.profile)
    app.assign_material(plan.core.name, plan.core.material.name)
    return (
        f"Core {plan.core.name} revolved and assigned {plan.core.material.name}."
        + enable_core_loss(
            app, plan.core.name, plan.core.material, plan.solution_type
        )
    )


def _stage_geometry_only_core(
    app: Maxwell3dApp,
    plan: GeometryOnlyMaxwell3dPlan,
) -> str:
    _create_core_geometry(app, plan.core_name, plan.core_profile)
    return f"Core {plan.core_name} revolved without a material assignment."


# Number of flat facets per conductor cross-section. 0 would keep a true circle.
#
# A round conductor gives Maxwell nothing but curved surfaces, and the DC-bias
# solve fails while mapping its DC field onto the AC mesh precisely there. 16
# facets plus the initial mesh settings below is the combination Fabio Posser
# verified solves on AEDT 2025 R2; the mesh settings alone with round wire do not.
# See docs/development/dc-bias-solve-limitation.md.
#
# Accepted cost: an inscribed 16-gon carries 97.4% of the copper of the wire
# circle, so reported DC resistance runs about 2.7% high. Fabio accepted that on
# 2026-07-28 in exchange for a solve that completes with full adaptivity. Raising
# this to 24 cuts the error to 1.1% if that ever matters.
CONDUCTOR_FACETS = 16

# Initial mesh settings. TAU with curvilinear meshing disabled is what makes the
# DC-bias solve complete; Maxwell 2D offers neither TAU nor the curvilinear
# switch, so the 2D adapter applies only the slider level.
INITIAL_MESH_METHOD = "AnsoftTAU"


def _create_winding_geometry(
    app: Maxwell3dApp,
    windings: tuple[WindingGroupPlan, ...] | tuple[GeometryOnlyWindingPlan, ...],
    *,
    material: str | None,
) -> int:
    count = 0
    for group in windings:
        for turn in group.turns:
            data = polyline_data(turn.segments, closed=True)
            kwargs: dict[str, Any] = {
                "points": [list(point) for point in data.points],
                "segment_type": list(data.kinds),
                "name": turn.name,
                "xsection_type": "Circle",
                "xsection_width": turn.bare_diameter_m,
                "xsection_num_seg": CONDUCTOR_FACETS,
            }
            if material is not None:
                kwargs["material"] = material
            app.modeler.create_polyline(**kwargs)
            count += 1
    return count


def _stage_windings(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    count = _create_winding_geometry(
        app,
        plan.windings,
        material=COPPER_MATERIAL,
    )
    return f"{count} turn conductors created."


def _stage_geometry_only_windings(
    app: Maxwell3dApp,
    plan: GeometryOnlyMaxwell3dPlan,
) -> str:
    count = _create_winding_geometry(app, plan.windings, material=None)
    return f"{count} winding solids created without material arguments."


def _stage_terminals(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    count = 0
    for group in plan.windings:
        for turn in group.turns:
            disk = turn.terminal.disk
            radial = math.hypot(disk.center.x, disk.center.y)
            app.modeler.create_circle(
                orientation="YZ",
                origin=[round(radial, 9), 0.0, disk.center.z],
                radius=disk.radius_m,
                # The terminal must lie on the conductor's end face, so it has to
                # be faceted exactly like the conductor cross-section.
                num_sides=CONDUCTOR_FACETS,
                name=turn.terminal.name,
            )
            app.modeler.rotate(turn.terminal.name, axis="Z", angle=disk.station_deg)
            count += 1
    return f"{count} terminal sheets created."


def _native_dc_active(plan: Maxwell3dDesignPlan) -> bool:
    return (
        plan.dc_bias is not None
        and plan.dc_bias.strategy is DcBiasStrategy.NATIVE_INCLUDE_DC_FIELDS
        and any(group.dc_current_a != 0.0 for group in plan.windings)
    )


def _stage_excitations(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    dc_applied = 0
    for group in plan.windings:
        coil_names: list[str] = []
        for turn in group.turns:
            coil = f"{turn.name}_Coil"
            app.assign_coil(
                turn.terminal.name,
                conductors_number=1,
                polarity=turn.terminal.polarity.value,
                name=coil,
            )
            coil_names.append(coil)
        winding = app.assign_winding(
            assignment=None,
            winding_type="Current",
            is_solid=group.is_solid,
            current=group.current_peak_a,
            phase=group.phase_deg,
            name=group.name,
        )
        if _native_dc_active(plan) and group.dc_current_a != 0.0:
            winding.props["DC Current"] = f"{group.dc_current_a:g}A"
            winding.update()
            dc_applied += 1
        app.add_winding_coils(assignment=group.name, coils=coil_names)
    message = f"{len(plan.windings)} windings excited."
    if dc_applied:
        message += f" DC applied to {dc_applied} windings."
    return message


def _stage_eddy(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    solid = [t.name for g in plan.windings if g.is_solid for t in g.turns]
    stranded = [t.name for g in plan.windings if not g.is_solid for t in g.turns]
    if solid:
        app.eddy_effects_on(solid, enable_eddy_effects=True)
    if stranded:
        app.eddy_effects_on(stranded, enable_eddy_effects=False)
    return f"Eddy effects: {len(solid)} solid on, {len(stranded)} stranded off."


def _stage_region(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    pad = plan.region.padding_percent
    region = app.modeler.create_air_region(pad, pad, pad, pad, pad, pad)
    if not region:
        raise RuntimeError("create_air_region returned no region object.")
    return f"Air region with {pad:g}% padding."


def _stage_mesh(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    # Initial mesh settings that make an 'AC Magnetic with DC' solve succeed on
    # this geometry, verified live by Fabio Posser and read back from his saved
    # project. Curvilinear meshing is the decisive one: it produces curved
    # elements on curved surfaces, and the DC-to-AC field mapping fails on
    # exactly those. See docs/development/dc-bias-solve-limitation.md.
    app.mesh.assign_initial_mesh_from_slider(
        level=INITIAL_MESH_SLIDER_LEVEL,
        method=INITIAL_MESH_METHOD,
        curvilinear=False,
        dynamic_surface=False,
        flex_mesh=False,
        auto_model_resolution=True,
    )
    conductors = [t.name for g in plan.windings for t in g.turns]
    app.mesh.assign_length_mesh(
        conductors, maximum_length=plan.mesh.conductor_max_length_m, name="ConductorLength"
    )
    app.mesh.assign_length_mesh(
        [plan.core.name], maximum_length=plan.mesh.core_max_length_m, name="CoreLength"
    )
    return (
        f"Initial mesh {INITIAL_MESH_METHOD} slider {INITIAL_MESH_SLIDER_LEVEL}, "
        "curvilinear off; length-based mesh restrictions assigned."
    )


def _stage_setup(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    setup = app.create_setup(name=plan.setup.name)
    setup.props["Frequency"] = f"{plan.setup.frequency_hz:g}Hz"
    setup.props["MaximumPasses"] = plan.setup.maximum_passes
    setup.props["PercentError"] = plan.setup.percent_error
    setup.update()
    return f"Setup {plan.setup.name} at {plan.setup.frequency_hz:g} Hz."


def _stage_matrix(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    # ponytail: pyaedt's assign_matrix() dispatcher lacks "AC Magnetic with DC"
    # support; the raw AEDT API call is live-verified to work for both 3D
    # solution types, so we bypass the pyaedt schema helper entirely.
    entries: list[object] = ["NAME:MatrixEntry"]
    for group in plan.windings:
        entries.append(["NAME:MatrixEntry", "Source:=", group.name])
    module = app.odesign.GetModule("MaxwellParameterSetup")
    module.AssignMatrix([f"NAME:{plan.matrix_name}", entries])
    return f"Matrix {plan.matrix_name} over {len(plan.windings)} windings."


def _stage_reports(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    for report in plan.reports:
        app.post.create_report(expressions=[report.expression], plot_name=report.name)
    return f"{len(plan.reports)} reports requested."


def _stage_validate(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    if app.validate_simple() != 1:
        raise RuntimeError("Design validation failed.")
    return "Design validation passed."


def _stage_analyze(
    app: Maxwell3dApp,
    plan: Maxwell3dDesignPlan,
    cancellation: CancellationToken | None = None,
) -> str:
    analyze_watched(app, plan.setup.name, cancellation=cancellation)
    return f"Solved {plan.setup.name}: {app.setup_convergence(plan.setup.name)}."


_STAGES: tuple[tuple[str, Any], ...] = (
    ("units", _stage_units),
    ("materials", _stage_materials),
    ("core", _stage_core),
    ("windings", _stage_windings),
    ("terminals", _stage_terminals),
    ("excitations", _stage_excitations),
    ("eddy", _stage_eddy),
    ("region", _stage_region),
    ("mesh", _stage_mesh),
    ("setup", _stage_setup),
    ("matrix", _stage_matrix),
    ("reports", _stage_reports),
    ("validate", _stage_validate),
)


def _stages_with_sections(
    sheets: SectionSheets, solve: bool
) -> tuple[tuple[str, Any], ...]:
    """`_STAGES`, with sheet creation before the solve when there will be one.

    A Generate Only run reads no fields, so it creates no sheets: the design a
    user opens afterwards carries only the model geometry.
    """
    if not solve:
        return _STAGES
    index = [name for name, _ in _STAGES].index("setup")
    return (
        *_STAGES[:index],
        ("sections", sheets.create),
        *_STAGES[index:],
    )



class SectionSheets:
    """The non-model cut sheets B and J are read on, created before the solve.

    What actually broke sheet creation was the sheet *name*: ids like
    `core.00.span-start` reached AEDT with the hyphen intact, which it refuses in
    an object name (see `section_sheets._sheet_name`). Creating them here rather
    than in the results phase is a separate, smaller point -- adding geometry to
    a design that has already solved invalidates its solution, and these sheets
    exist to be read against that solution. They are non-model, so they are
    excluded from the mesh and creating them early changes nothing about it.

    Creation failures never fail the run: the sheets serve field extraction
    only, so the error rides along as a diagnostic and the field quantities
    normalize to unavailable with a reason.
    """

    def __init__(self) -> None:
        self.core: tuple[EvaluatedArea, ...] = ()
        self.conductors: tuple[EvaluatedArea, ...] = ()
        self.diagnostic: str | None = None

    def create(self, app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
        try:
            self.core = create_core_section_sheets(
                app,
                plan.core,
                plan.core_sections,
                r_inner_m=plan.core.r_inner_m,
                r_outer_m=plan.core.r_outer_m,
                half_height_m=plan.core.half_height_m,
            )
            self.conductors = create_conductor_section_sheets(
                app, plan.conductor_sections
            )
        except Exception as error:  # noqa: BLE001 - no sheets means no field values
            self.diagnostic = f"{type(error).__name__}: {error}"
            return f"No field section sheets: {self.diagnostic}"
        return (
            f"{len(self.core)} core and {len(self.conductors)} conductor "
            "section sheets created as non-model."
        )


def _with_field_sections(
    app: Maxwell3dApp,
    plan: Maxwell3dDesignPlan,
    raw: RawScalarResults,
    sheets: SectionSheets,
) -> RawScalarResults:
    """Read B and J on the sheets the sections stage already created.

    Each field read is guarded individually inside ``read_field_areas``.
    """
    from dataclasses import replace

    if sheets.diagnostic is not None:
        return replace(raw, diagnostics=raw.diagnostics + (sheets.diagnostic,))
    return replace(
        raw,
        flux_density_sections=read_field_areas(
            app, sheets.core, FLUX_DENSITY_QUANTITY
        ),
        current_density_sections=read_field_areas(
            app, sheets.conductors, CURRENT_DENSITY_QUANTITY
        ),
    )


class PyaedtMaxwell3dExporter:
    """Executes a Maxwell3dDesignPlan as named stages; never reports a partial design."""

    def __init__(self, app_factory: Maxwell3dAppFactory | None = None) -> None:
        self._factory = DefaultMaxwell3dAppFactory() if app_factory is None else app_factory

    def export(self, request: Maxwell3dExportRequest) -> Maxwell3dExportResult:
        request.output_directory.mkdir(parents=True, exist_ok=True)
        project_path = request.output_directory / f"{request.project_name}.aedt"
        project_path.unlink(missing_ok=True)
        plan = request.plan
        stages: list[StageRecord] = []
        raw_results: RawScalarResults | None = None

        def result() -> Maxwell3dExportResult:
            return Maxwell3dExportResult(
                project_path=project_path,
                design_name=plan.design_name,
                pyaedt_version=self._factory.pyaedt_version,
                stages=tuple(stages),
                raw_results=raw_results,
            )

        _emit(request.progress, "launch", StagePhase.STARTED, None)
        try:
            app = self._factory.create(
                project=str(project_path),
                design=plan.design_name,
                solution_type=plan.solution_type,
                version=str(request.release),
                non_graphical=request.non_graphical,
                new_desktop=True,
                close_on_exit=False,
                student_version=request.edition.value == "student",
            )
        except Exception as error:  # noqa: BLE001 - stage boundary converts to record
            stages.append(StageRecord(name="launch", succeeded=False, message=str(error)))
            _emit(request.progress, "launch", StagePhase.FAILED, str(error))
            return result()
        launch_message = f"Maxwell 3D design {plan.design_name!r} opened."
        stages.append(
            StageRecord(name="launch", succeeded=True, message=launch_message)
        )
        _emit(request.progress, "launch", StagePhase.SUCCEEDED, launch_message)
        try:
            cancelled_before: str | None = None
            sheets = SectionSheets()
            for name, stage in _stages_with_sections(sheets, request.solve):
                if _cancelled(request.cancellation):
                    cancelled_before = name
                    break
                _emit(request.progress, name, StagePhase.STARTED, None)
                try:
                    message = stage(app, plan)
                except Exception as error:  # noqa: BLE001 - stage boundary
                    stages.append(StageRecord(name=name, succeeded=False, message=str(error)))
                    _emit(request.progress, name, StagePhase.FAILED, str(error))
                    try:
                        app.save_project(str(project_path))
                        stages.append(
                            StageRecord(
                                name="save",
                                succeeded=True,
                                message="Diagnostic save after failed stage.",
                            )
                        )
                    except Exception as save_error:  # noqa: BLE001 - stage boundary
                        stages.append(
                            StageRecord(name="save", succeeded=False, message=str(save_error))
                        )
                    # After the save, so anything the save itself told AEDT's
                    # channel is captured too; still before the release.
                    _log_desktop_messages(app, name)
                    return result()
                stages.append(StageRecord(name=name, succeeded=True, message=message))
                _emit(request.progress, name, StagePhase.SUCCEEDED, message)
            # The save runs even after cancellation: an interrupted run still
            # keeps whatever the design reached, it just never claims success.
            _emit(request.progress, "save", StagePhase.STARTED, None)
            try:
                saved = bool(app.save_project(str(project_path)))
                save_message = "Project saved." if saved else "save_project returned False."
                stages.append(
                    StageRecord(name="save", succeeded=saved, message=save_message)
                )
                _emit(
                    request.progress,
                    "save",
                    StagePhase.SUCCEEDED if saved else StagePhase.FAILED,
                    save_message,
                )
            except Exception as error:  # noqa: BLE001 - stage boundary
                stages.append(StageRecord(name="save", succeeded=False, message=str(error)))
                _emit(request.progress, "save", StagePhase.FAILED, str(error))
                _log_desktop_messages(app, "save")
                return result()
            if cancelled_before is None and request.solve:
                if _cancelled(request.cancellation):
                    cancelled_before = "analyze"
                else:
                    _emit(request.progress, "analyze", StagePhase.STARTED, None)
                    try:
                        message = _stage_analyze(app, plan, request.cancellation)
                    except RunCancelled:
                        # The solve itself was stopped, so there is nothing to
                        # read; the run ends cancelled, not failed.
                        cancelled_before = "analyze"
                    except Exception as error:  # noqa: BLE001 - stage boundary
                        stages.append(
                            StageRecord(name="analyze", succeeded=False, message=str(error))
                        )
                        _emit(request.progress, "analyze", StagePhase.FAILED, str(error))
                        _log_desktop_messages(app, "analyze")
                        return result()
                    else:
                        stages.append(
                            StageRecord(name="analyze", succeeded=True, message=message)
                        )
                        _emit(request.progress, "analyze", StagePhase.SUCCEEDED, message)
                        # Extraction never fails a solved run: a read error rides
                        # along as a diagnostic and normalizes to unavailable.
                        _emit(request.progress, "results", StagePhase.STARTED, None)
                        raw_results = read_scalar_results(
                            app,
                            matrix_name=plan.matrix_name,
                            winding_names=tuple(group.name for group in plan.windings),
                            setup_name=plan.setup.name,
                            frequency_hz=plan.setup.frequency_hz,
                        )
                        raw_results = _with_field_sections(app, plan, raw_results, sheets)
                        results_message = _results_message(raw_results)
                        stages.append(
                            StageRecord(
                                name="results", succeeded=True, message=results_message
                            )
                        )
                        _emit(
                            request.progress,
                            "results",
                            StagePhase.SUCCEEDED,
                            results_message,
                        )
            if cancelled_before is not None:
                _record_cancellation(stages, request.progress, cancelled_before)
        finally:
            release_live_app(app)
        return result()

    def export_geometry_only(
        self,
        request: Maxwell3dGeometryOnlyRequest,
    ) -> Maxwell3dExportResult:
        request.output_directory.mkdir(parents=True, exist_ok=True)
        project_path = request.output_directory / f"{request.project_name}.aedt"
        project_path.unlink(missing_ok=True)
        plan = request.plan
        stages: list[StageRecord] = []

        def result() -> Maxwell3dExportResult:
            return Maxwell3dExportResult(
                project_path=project_path,
                design_name=request.design_name,
                pyaedt_version=self._factory.pyaedt_version,
                stages=tuple(stages),
            )

        try:
            app = self._factory.create(
                project=str(project_path),
                design=request.design_name,
                version=str(request.release),
                non_graphical=request.non_graphical,
                new_desktop=True,
                close_on_exit=False,
                student_version=request.edition.value == "student",
            )
        except Exception as error:  # noqa: BLE001 - stage boundary converts to record
            stages.append(StageRecord(name="launch", succeeded=False, message=str(error)))
            return result()
        stages.append(
            StageRecord(
                name="launch",
                succeeded=True,
                message=f"Maxwell 3D geometry-only design {request.design_name!r} opened.",
            )
        )
        geometry_stages = (
            ("units", _stage_units),
            ("core", _stage_geometry_only_core),
            ("windings", _stage_geometry_only_windings),
        )
        try:
            for name, stage in geometry_stages:
                try:
                    message = stage(app, plan)
                except Exception as error:  # noqa: BLE001 - stage boundary
                    stages.append(StageRecord(name=name, succeeded=False, message=str(error)))
                    try:
                        app.save_project(str(project_path))
                        stages.append(
                            StageRecord(
                                name="save",
                                succeeded=True,
                                message="Diagnostic save after failed geometry stage.",
                            )
                        )
                    except Exception as save_error:  # noqa: BLE001 - stage boundary
                        stages.append(
                            StageRecord(name="save", succeeded=False, message=str(save_error))
                        )
                    _log_desktop_messages(app, name)
                    return result()
                stages.append(StageRecord(name=name, succeeded=True, message=message))
            try:
                saved = bool(app.save_project(str(project_path)))
                stages.append(
                    StageRecord(
                        name="save",
                        succeeded=saved,
                        message="Project saved." if saved else "save_project returned False.",
                    )
                )
            except Exception as error:  # noqa: BLE001 - stage boundary
                stages.append(StageRecord(name="save", succeeded=False, message=str(error)))
                _log_desktop_messages(app, "save")
        finally:
            release_live_app(app)
        return result()
