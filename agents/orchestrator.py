"""
Master Orchestrator Agent for Irona KiCad 10
Powered by Google Gemini (with deterministic heuristic fallback).
Deconstructs natural language hardware specs into circuit topology, electrical constraints, and BOM.
"""

import os
import sys
import re
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.state import IronaAgentState, HardwareRequirements, ComponentSpec

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MasterOrchestrator")


class MasterOrchestratorAgent:
    """Master reasoning agent orchestrating hardware design decisions."""

    def __init__(self, model_name: str = "gemini-2.5-pro"):
        self.model_name = model_name
        self.gemini_api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        self.llm = None
        self._init_llm()

    def _init_llm(self) -> None:
        if self.gemini_api_key:
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
                self.llm = ChatGoogleGenerativeAI(
                    model=self.model_name,
                    google_api_key=self.gemini_api_key,
                    temperature=0.1
                )
                logger.info(f"Initialized Gemini Orchestrator: {self.model_name}")
            except Exception as e:
                logger.warning(f"Could not initialize ChatGoogleGenerativeAI: {e}")
                self.llm = None
        else:
            logger.info("No Gemini API key found in environment. Using deterministic hardware synthesis engine.")

    def parse_spec_and_plan(self, state: IronaAgentState) -> IronaAgentState:
        """
        Extracts electrical requirements and formulates the initial BOM from the spec prompt.
        """
        prompt = state["spec_prompt"]
        logger.info(f"Orchestrator analyzing spec prompt: '{prompt}'")

        # 1. If LLM is available, query Gemini for structured hardware breakdown
        if self.llm:
            try:
                sys_msg = (
                    "You are an expert EDA Electrical Engineer and Circuit Designer. "
                    "Analyze the user's hardware specification and output a strict JSON object with: "
                    "circuit_type, vin_nominal_v, vout_target_v, iout_max_a, switching_freq_khz, and bom (array of ref, mpn, value, package, category)."
                )
                response = self.llm.invoke(f"{sys_msg}\n\nUser Specification: {prompt}")
                content = response.content
                # Extract JSON block
                m = re.search(r'\{.*\}', content, re.DOTALL)
                if m:
                    parsed = json.loads(m.group(0))
                    state["requirements"] = {
                        "circuit_type": parsed.get("circuit_type", "Buck_Converter"),
                        "vin_nominal_v": float(parsed.get("vin_nominal_v", 12.0)),
                        "vout_target_v": float(parsed.get("vout_target_v", 3.3)),
                        "iout_max_a": float(parsed.get("iout_max_a", 2.0)),
                        "switching_freq_khz": float(parsed.get("switching_freq_khz", 500.0)),
                        "ambient_temp_c": 25.0,
                        "max_allowed_temp_c": 85.0
                    }
                    state["bom"] = parsed.get("bom", self._synthesize_default_bom())
                    state["messages"].append({"role": "orchestrator", "content": "Gemini extracted requirements and formulated BOM."})
                    return state
            except Exception as e:
                logger.warning(f"Gemini LLM inference fallback triggered: {e}")

        # 2. Deterministic EDA extraction fallback
        vin = 12.0
        vout = 3.3
        iout = 2.0

        # Regex parsing for voltages and currents
        m_vin = re.search(r'(\d+(?:\.\d+)?)\s*V(?:\s*to|\s*in|\s*input)', prompt, re.IGNORECASE)
        if m_vin:
            vin = float(m_vin.group(1))

        m_vout = re.search(r'(?:to|output|\->)\s*(\d+(?:\.\d+)?)\s*V', prompt, re.IGNORECASE)
        if m_vout:
            vout = float(m_vout.group(1))

        m_iout = re.search(r'(\d+(?:\.\d+)?)\s*(?:A|Amps)', prompt, re.IGNORECASE)
        if m_iout:
            iout = float(m_iout.group(1))

        state["requirements"] = {
            "circuit_type": "Synchronous_Buck_Converter",
            "vin_nominal_v": vin,
            "vout_target_v": vout,
            "iout_max_a": iout,
            "switching_freq_khz": 500.0,
            "ambient_temp_c": 25.0,
            "max_allowed_temp_c": 85.0
        }
        state["bom"] = self._synthesize_default_bom(vin, vout, iout)
        state["messages"].append({
            "role": "orchestrator",
            "content": f"Formulated design plan for {vin}V -> {vout}V @ {iout}A Buck Converter with {len(state['bom'])} components."
        })
        return state

    def _synthesize_default_bom(self, vin: float = 12.0, vout: float = 3.3, iout: float = 2.0) -> List[Dict[str, Any]]:
        """Generates standard tested BOM for synchronous buck converter."""
        # Calculate feedback resistors for 0.596V Vref
        # Vout = 0.596 * (1 + R1/R2) => R1 = R2 * (Vout/0.596 - 1)
        r2_val = 10.0  # 10k
        r1_val = round(r2_val * (vout / 0.596 - 1), 1)

        return [
            {"ref": "J1", "mpn": "Power_In_2P", "value": "Power_In", "package": "CONN_2P", "category": "CONNECTOR"},
            {"ref": "C1", "mpn": "C0805_10uF", "value": f"10uF/{int(vin*1.5)}V", "package": "0805", "category": "CAPACITOR"},
            {"ref": "C2", "mpn": "C0805_100nF", "value": f"100nF/{int(vin*2)}V", "package": "0805", "category": "CAPACITOR"},
            {"ref": "U1", "mpn": "TPS54202", "value": "TPS54202", "package": "SOT23-6", "category": "IC"},
            {"ref": "C_BOOT", "mpn": "C0805_100nF", "value": "100nF", "package": "0805", "category": "CAPACITOR"},
            {"ref": "L1", "mpn": "L0805_4u7", "value": "4.7uH", "package": "0805", "category": "INDUCTOR"},
            {"ref": "R1", "mpn": "R0805_Feedback1", "value": f"{r1_val}k", "package": "0805", "category": "RESISTOR"},
            {"ref": "R2", "mpn": "R0805_Feedback2", "value": f"{r2_val}k", "package": "0805", "category": "RESISTOR"},
            {"ref": "C3", "mpn": "C0805_22uF", "value": f"22uF/{int(vout*2)}V", "package": "0805", "category": "CAPACITOR"},
            {"ref": "C4", "mpn": "C0805_22uF", "value": f"22uF/{int(vout*2)}V", "package": "0805", "category": "CAPACITOR"},
            {"ref": "J2", "mpn": "Power_Out_2P", "value": "Power_Out", "package": "CONN_2P", "category": "CONNECTOR"},
        ]
