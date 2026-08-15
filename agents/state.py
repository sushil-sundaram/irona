"""
Multi-Agent State Schema for Irona KiCad 10
Defines the shared LangGraph state dictionary and Pydantic models.
"""

from typing import Dict, Any, List, Optional, TypedDict, Union

try:
    from pydantic import BaseModel, Field
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False
    from dataclasses import dataclass, field

if HAS_PYDANTIC:
    class ComponentSpec(BaseModel):
        ref: str
        mpn: str
        value: str
        package: str
        category: str = "IC"
        description: str = ""
        pins: List[Dict[str, Any]] = Field(default_factory=list)

    class HardwareRequirements(BaseModel):
        circuit_type: str = "Buck_Converter"
        vin_nominal_v: float = 12.0
        vout_target_v: float = 3.3
        iout_max_a: float = 2.0
        switching_freq_khz: float = 500.0
        max_ripple_mv: float = 30.0
        ambient_temp_c: float = 25.0
        max_allowed_temp_c: float = 85.0
else:
    @dataclass
    class ComponentSpec:
        ref: str
        mpn: str
        value: str
        package: str
        category: str = "IC"
        description: str = ""
        pins: List[Dict[str, Any]] = field(default_factory=list)

    @dataclass
    class HardwareRequirements:
        circuit_type: str = "Buck_Converter"
        vin_nominal_v: float = 12.0
        vout_target_v: float = 3.3
        iout_max_a: float = 2.0
        switching_freq_khz: float = 500.0
        max_ripple_mv: float = 30.0
        ambient_temp_c: float = 25.0
        max_allowed_temp_c: float = 85.0


class IronaAgentState(TypedDict):
    """
    LangGraph TypedDict State passed across multi-agent nodes.
    """
    project_name: str
    project_dir: str
    spec_prompt: str
    requirements: Dict[str, Any]
    bom: List[Dict[str, Any]]
    libraries_registered: bool
    schematic_path: Optional[str]
    netlist_path: Optional[str]
    pcb_path: Optional[str]
    spatial_layout_plan: Dict[str, Any]
    physics_results: Optional[Dict[str, Any]]
    physics_passed: bool
    iteration_count: int
    max_iterations: int
    messages: List[Dict[str, str]]
    errors: List[str]
    status: str
