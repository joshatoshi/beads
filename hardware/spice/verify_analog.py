#!/usr/bin/env python3
"""ngspice verification suite for the Beads Pedalboard Skiff analog, power, USB-isolation,
popless PhotoMOS relay bypass, stereo guitar unity staging, +-8V CV DAC, and +3.3V ADC clamp.

Derives component values directly from hardware/main_board/main_board.net so netlist drift
is immediately caught, and executes ngspice in batch mode across 7 quantitative checks.
"""
from __future__ import annotations

import math
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
NETLIST_PATH = ROOT / "hardware" / "main_board" / "main_board.net"
SCRATCH = pathlib.Path("/tmp/opencode/beads_spice")
SCRATCH.mkdir(parents=True, exist_ok=True)


def parse_value_ohms(val: str) -> float:
    val = val.strip().upper().replace("Ω", "").replace("OHM", "")
    m = re.match(r"^([0-9.]+)\s*([RKM]?)$", val)
    if not m:
        raise ValueError(f"Cannot parse resistor value: {val}")
    num = float(m.group(1))
    mul = {"": 1.0, "R": 1.0, "K": 1e3, "M": 1e6}[m.group(2)]
    return num * mul


def parse_cap_farads(val: str) -> float:
    m = re.match(r"^([0-9.]+)\s*(pF|nF|uF|µF)", val, re.I)
    if not m:
        raise ValueError(f"Cannot parse cap value: {val}")
    num = float(m.group(1))
    unit = m.group(2).lower()
    mul = {"pf": 1e-12, "nf": 1e-9, "uf": 1e-6, "µf": 1e-6}[unit]
    return num * mul


def load_netlist_values() -> dict[str, str]:
    if not NETLIST_PATH.exists():
        raise FileNotFoundError(f"Missing netlist: {NETLIST_PATH}")
    txt = NETLIST_PATH.read_text(encoding="utf-8")
    vals = {}
    for m in re.finditer(r'\(comp \(ref "([^"]+)"\)\s+\(value "([^"]+)"\)', txt):
        vals[m.group(1)] = m.group(2)
    return vals


def load_netlist_pin_nets() -> dict[tuple[str, str], str]:
    txt = NETLIST_PATH.read_text(encoding="utf-8")
    nets_sec = txt[txt.find("(nets"):]
    pin_map: dict[tuple[str, str], str] = {}
    for m in re.finditer(r'\(net \(code "\d+"\) \(name "([^"]+)"\)(.*?)(?=\n    \(net |\n  \)\n\))', nets_sec, re.S):
        net_name, body = m.group(1), m.group(2)
        for nm in re.finditer(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', body):
            pin_map[(nm.group(1), nm.group(2))] = net_name
    return pin_map


def run_ngspice(name: str, deck: str) -> dict[str, float]:
    cir = SCRATCH / f"{name}.cir"
    cir.write_text(deck, encoding="utf-8")
    proc = subprocess.run(
        ["ngspice", "-b", str(cir)],
        capture_output=True,
        text=True,
        check=False,
    )
    out = proc.stdout + "\n" + proc.stderr
    if proc.returncode != 0:
        raise RuntimeError(f"ngspice failed for {name} (rc={proc.returncode}):\n{out}")
    meas: dict[str, float] = {}
    for line in out.splitlines():
        m = re.match(r"^\s*([a-z0-9_]+)\s*=\s*([+-]?[0-9.]+(?:e[+-]?\d+)?)", line.strip(), re.I)
        if m:
            try:
                meas[m.group(1).lower()] = float(m.group(2))
            except ValueError:
                pass
    return meas


def test_1_rpp_and_gate_clamp(vals: dict[str, str]) -> None:
    r1 = parse_value_ohms(vals["R1"])
    r2 = parse_value_ohms(vals["R2"])
    # Check 9V fwd, 18V fwd, 24V surge, and -18V reverse polarity on AO3401A + BZX84-C9V1
    results = {}
    for tag, vin in [("fwd9", 9.0), ("fwd18", 18.0), ("surge24", 24.0), ("rev18", -18.0)]:
        deck = f"""* Beads Test 1: AO3401A Reverse-Polarity Protection & 9.1V Zener Gate Clamp ({tag})
.model PMOS_AO3401 PMOS(VTO=-1.1 KP=12 LAMBDA=0.02 RD=0.02 RS=0.02 IS=1e-13)
.model D_BODY D(IS=1e-12 N=1.05 RS=0.05 BV=30)
.model D_Z9V1 D(IS=1e-14 N=1.05 RS=10 BV=9.05 IBV=5m)
V_IN vin_raw 0 DC {vin}
R_PTC vin_raw vin_fused 0.12
* AO3401A: D=vin_fused, G=rpp_gate, S=vin_prot, B=vin_prot (body diode D->S)
M_RPP vin_fused rpp_gate vin_prot vin_prot PMOS_AO3401 W=1 L=1
D_RPP_BD vin_fused vin_prot D_BODY
R1 vin_prot rpp_gate {r1}
R2 rpp_gate 0 {r2}
* BZX84-C9V1: A=rpp_gate, K=vin_prot
D_Z rpp_gate vin_prot D_Z9V1
R_LOAD vin_prot 0 60
.op
.control
op
let v_prot = v(vin_prot)
let v_sg = v(vin_prot) - v(rpp_gate)
let i_in = -i(V_IN)
print v_prot v_sg i_in
quit
.endc
.end
"""
        results[tag] = run_ngspice(f"t1_{tag}", deck)

    assert results["fwd9"]["v_prot"] >= 8.80, f"9V RPP drop too high: {results['fwd9']}"
    assert 4.0 <= results["fwd9"]["v_sg"] <= 9.15, f"9V Vsg out of range: {results['fwd9']}"
    assert results["fwd18"]["v_prot"] >= 17.80, f"18V RPP drop too high: {results['fwd18']}"
    assert 8.0 <= results["fwd18"]["v_sg"] <= 9.15, f"18V Vsg exceeded clamp: {results['fwd18']}"
    assert results["surge24"]["v_sg"] <= 9.50, f"24V surge Vsg exceeded 12V abs-max: {results['surge24']}"
    assert abs(results["rev18"]["i_in"]) < 1e-6, f"-18V reverse current leaked: {results['rev18']}"
    assert results["rev18"]["v_prot"] > -0.05, f"-18V leaked to downstream rail: {results['rev18']}"
    print(
        f"[PASS] Test 1 (RPP + 9.1V Gate Clamp): "
        f"9V->Vprot={results['fwd9']['v_prot']:.3f}V Vsg={results['fwd9']['v_sg']:.3f}V | "
        f"18V->Vprot={results['fwd18']['v_prot']:.3f}V Vsg={results['fwd18']['v_sg']:.3f}V | "
        f"24V->Vsg={results['surge24']['v_sg']:.3f}V | "
        f"-18V->Irev={results['rev18']['i_in']*1e9:.2f}nA"
    )


def test_2_usb_isolation(vals: dict[str, str], pin_nets: dict[tuple[str, str], str]) -> None:
    # Verify netlist topology: D_OR_PED (1N5819WS) replaces Q_PED_OR/Q_PED_DRV/R28,
    # U_LVL (SN74AHCT541PWR) translates 3.3V->5V SPI/CS, R77..R80 pull up to +5V_BUCK (NOT +3V3_DIG!),
    # and U_USB_ESD (SRV05-4) + R23 (27R) + R25/R26 (VBUS_DET) match the schematic netlist.
    assert vals.get("D_OR_PED") == "1N5819WS", f"Expected D_OR_PED=1N5819WS, got {vals.get('D_OR_PED')}"
    for forbidden in ("Q_PED_OR", "Q_PED_DRV", "R28"):
        assert forbidden not in vals, f"Forbidden back-power latch-up part {forbidden} still in netlist!"
    assert vals.get("U_LVL") == "SN74AHCT541PWR", f"Expected U_LVL=SN74AHCT541PWR, got {vals.get('U_LVL')}"
    assert vals.get("U_USB_ESD") == "SRV05-4-P-T7", f"Expected U_USB_ESD=SRV05-4-P-T7, got {vals.get('U_USB_ESD')}"
    assert pin_nets[("D_OR_PED", "2")] == "+5V_BUCK" and pin_nets[("D_OR_PED", "1")] == "VIN_3V3_LDO"
    assert pin_nets[("U_LVL", "20")] == "+5V_BUCK" and pin_nets[("U_LVL", "10")] == "GND"
    assert pin_nets[("U_USB_ESD", "5")] == "USB_VBUS" and pin_nets[("U_USB_ESD", "2")] == "GND"
    assert pin_nets[("U_USB_ESD", "3")] == "USB_DP_CON" and pin_nets[("U_USB_ESD", "4")] == "USB_DP_CON"
    assert pin_nets[("R23", "1")] == "USB_DP_CON" and pin_nets[("R23", "2")] == "USB_DP"
    assert pin_nets[("R25", "1")] == "USB_VBUS" and pin_nets[("R25", "2")] == "VBUS_DET"
    assert pin_nets[("R26", "1")] == "VBUS_DET" and pin_nets[("R26", "2")] == "GND"
    for rref, cs_net in [("R77", "DAC0_CS_N"), ("R78", "DAC1_CS_N"), ("R79", "DAC2_CS_N"), ("R80", "DAC3_CS_N")]:
        assert pin_nets[(rref, "1")] == "+5V_BUCK", f"{rref}.1 must tie to +5V_BUCK, got {pin_nets[(rref, '1')]}"
        assert pin_nets[(rref, "2")] == cs_net, f"{rref}.2 must tie to {cs_net}, got {pin_nets[(rref, '2')]}"
    for i in range(4):
        assert pin_nets[(f"U_DAC{i}", "3")] == "DAC_SPI_SCK"
        assert pin_nets[(f"U_DAC{i}", "4")] == "DAC_SPI_MOSI"
        assert pin_nets[(f"U_DAC{i}", "2")] == f"DAC{i}_CS_N"

    r27 = parse_value_ohms(vals["R27"])
    r3 = parse_value_ohms(vals["R3"])
    r23 = parse_value_ohms(vals["R23"])
    r24 = parse_value_ohms(vals["R24"])
    r25 = parse_value_ohms(vals["R25"])
    r26 = parse_value_ohms(vals["R26"])
    r_cs_pu = parse_value_ohms(vals["R77"])

    def sim_mode(
        tag: str,
        v_buck_src: float | None,
        v_usb_src: float | None,
        usb_open: bool = False,
        pullup_gated: bool = True,
    ) -> dict[str, float]:
        buck_elem = (
            f"V_BUCK v5_buck 0 DC {v_buck_src}"
            if v_buck_src is not None
            else f"V_BUCK_SENSE v5_buck v5_bleed DC 0\nR_BLEED v5_bleed 0 {r3}"
        )
        if usb_open:
            usb_elem = "V_USB usb_vbus_raw usb_open_n DC 0\nR_USB_OPEN usb_open_n 0 1G"
        elif v_usb_src is not None:
            usb_elem = f"V_USB usb_vbus_raw 0 DC {v_usb_src}"
        else:
            usb_elem = "V_USB usb_vbus_raw 0 DC 0"
        i_buck_expr = "-i(V_BUCK)" if v_buck_src is not None else "i(V_BUCK_SENSE)"
        # RP2040 internal 1.5 kOhm D+ pull-up: when gated by PIN_VBUS_DET, SW_DP_PU conducts ONLY when VBUS_DET > 1.8V;
        # when ungated (bug regression check), SW_DP_PU is forced ON whenever +3V3_DIG is up.
        if pullup_gated:
            pu_elem = (
                ".model SW_VBUS_PU SW(RON=1.5k ROFF=1G VT=1.80 VH=0.10)\n"
                "S_DP_PU v3v3_dig usb_dp vbus_det 0 SW_VBUS_PU"
            )
        else:
            pu_elem = "R_DP_PU_UNGATED v3v3_dig usb_dp 1.5k"
        # Model +3V3_DIG (from AMS1117-3.3), F_USB, U_USB_ESD (SRV05-4 steering diodes IO2/IO3->VP),
        # R23/R24 (27R), R25/R26 (10k/15k VBUS_DET divider), R77..R80 pulled to +5V_BUCK, MCP4822 upper ESD
        # clamp diodes to +5V_BUCK, and worst-case 3.3V inputs on SN74AHCT541.
        deck = f"""* Beads Test 2: Bidirectional <1uA USB-C VBUS <-> +5V_BUCK Isolation + SRV05-4 & VBUS_DET Pull-Up Audit ({tag})
.model PMOS_AO3401 PMOS(VTO=-1.1 KP=12 LAMBDA=0.02 RD=0.02 RS=0.02 IS=1e-13)
.model D_BODY D(IS=1e-12 N=1.05 RS=0.05)
* Hottech 1N5819WS (C191023) 25C datasheet fit: Vf=0.34V@50mA, Vf=0.54V@1A, Ir=200nA@5V
.model D_1N5819 D(IS=2.0e-7 N=1.05 RS=0.12 BV=40 IBV=500u)
.model D_ESD D(IS=1e-13 N=1.05 RS=2.0)
* Semtech/LCSC SRV05-4-P-T7 (C85364) steering diodes (IO -> VP, VN -> IO) + 6V TVS (VP -> VN)
.model D_SRV05 D(IS=2e-13 N=1.05 RS=0.8)
.model D_SRV05_TVS D(IS=1e-13 N=1.05 RS=0.5 BV=6.5 IBV=1m)
{buck_elem}
{usb_elem}
R_FUSB usb_vbus_raw usb_vbus 0.35
* VBUS_DET divider (R25=10k, R26=15k -> GPIO24)
R25 usb_vbus vbus_det {r25}
R26 vbus_det 0 {r26}
* U_USB_ESD (SRV05-4-P-T7): Pin 5 VP=USB_VBUS, Pin 2 VN=GND, IO2/IO3=USB_DP_CON, IO1/IO4=USB_DM_CON
D_SRV_DP_HI usb_dp_con usb_vbus D_SRV05
D_SRV_DP_LO 0 usb_dp_con D_SRV05
D_SRV_DM_HI usb_dm_con usb_vbus D_SRV05
D_SRV_DM_LO 0 usb_dm_con D_SRV05
D_SRV_TVS 0 usb_vbus D_SRV05_TVS
R23 usb_dp_con usb_dp {r23}
R24 usb_dm_con usb_dm {r24}
R_DM_LEAK usb_dm 0 100Meg
{pu_elem}
* USB power path: D_USB_FWD (1N5819WS) + Q_USB (AO3401A: D=usb_post, S=vin_3v3, G=R27->+5V_BUCK)
V_USB_PWR_SENSE usb_vbus usb_fwd_a DC 0
D_USB_FWD usb_fwd_a usb_post D_1N5819
M_QUSB usb_post q_usb_g vin_3v3 vin_3v3 PMOS_AO3401 W=1 L=1
D_QUSB_BD usb_post vin_3v3 D_BODY
R27 v5_buck q_usb_g {r27}
* Pedal path: D_OR_PED (1N5819WS per plan/01 §4: A=+5V_BUCK, K=VIN_3V3_LDO)
D_OR_PED v5_buck vin_3v3 D_1N5819
* AMS1117-3.3 LDO (50 mA digital load + regulated +3V3_DIG output when VIN_3V3_LDO > 4.2V)
R_LDO_LOAD vin_3v3 0 94
B_3V3 v3v3_dig 0 V = 3.30 * (0.5 + 0.5 * tanh(20 * (v(vin_3v3) - 4.2)))
* R77..R80 (4x 10k ~CS pull-ups on +5V_BUCK) + 4x MCP4822 ESD clamp diodes to +5V_BUCK
R77 v5_buck dac0_cs {r_cs_pu}
R78 v5_buck dac1_cs {r_cs_pu}
R79 v5_buck dac2_cs {r_cs_pu}
R80 v5_buck dac3_cs {r_cs_pu}
D_ESD0 dac0_cs v5_buck D_ESD
D_ESD1 dac1_cs v5_buck D_ESD
D_ESD2 dac2_cs v5_buck D_ESD
D_ESD3 dac3_cs v5_buck D_ESD
* SN74AHCT541 (U_LVL): 5.5V-tolerant inputs with ZERO upper diode to VCC (only <=0.1uA leakage to GND)
R_LVL_IN0 v3v3_dig 0 33Meg
R_LVL_IN1 v3v3_dig 0 33Meg
* Unpowered U_LVL output high-Z leakage to +5V_BUCK (< 10 nA)
R_LVL_Y0 dac0_cs 0 100Meg
R_LVL_Y1 dac1_cs 0 100Meg
R_LVL_Y2 dac2_cs 0 100Meg
R_LVL_Y3 dac3_cs 0 100Meg
.op
.control
op
let v_ldo = v(vin_3v3)
let v_3v3 = v(v3v3_dig)
let i_usb = -i(V_USB)
let i_usb_pwr = i(V_USB_PWR_SENSE)
let i_buck = {i_buck_expr}
let v_buck = v(v5_buck)
let v_vbus = v(usb_vbus)
let v_vbus_det = v(vbus_det)
let v_dp_con = v(usb_dp_con)
print v_ldo v_3v3 i_usb i_usb_pwr i_buck v_buck v_vbus v_vbus_det v_dp_con
quit
.endc
.end
"""
        return run_ngspice(f"t2_{tag}", deck)

    m_ped = sim_mode("pedal_only", 5.08, None)                       # Pedal ON, USB host powered off (0V)
    m_ped_open = sim_mode("pedal_unplugged", 5.08, None, usb_open=True)  # Pedal ON, USB cable unplugged
    m_ungated_0v = sim_mode("ungated_0v_proof", 5.08, None, pullup_gated=False)
    m_ungated_open = sim_mode("ungated_open_proof", 5.08, None, usb_open=True, pullup_gated=False)
    m_both = sim_mode("both_on", 5.08, 5.00)                         # Both Pedal 5.08V and USB 5.00V ON
    m_usb = sim_mode("usb_only", None, 5.00)                         # Pedal OFF (bleed to 0V), USB 5.00V ON

    # Confirm the ungated negative-control reproduces the exact ~1.7 mA backfeed & ~1.5 V latch fault!
    assert abs(m_ungated_0v["i_usb"]) > 1.5e-3, f"Expected ungated D+ pull-up backfeed >1.5mA, got {m_ungated_0v}"
    assert m_ungated_open["v_vbus_det"] > 1.40, f"Expected ungated open-cable VBUS_DET latch >1.4V, got {m_ungated_open}"

    # Verify VBUS_DET-gated firmware eliminates backfeed (< 1 uA) & floating VBUS (< 50 mV)!
    assert abs(m_ped["i_usb"]) < 1e-6, f"Pedal->USB backfeed >= 1uA: {m_ped}"
    assert m_ped["v_ldo"] >= 4.60, f"Pedal-only VIN_3V3_LDO too low for AMS1117: {m_ped}"
    assert m_ped_open["v_vbus"] < 0.05 and m_ped_open["v_vbus_det"] < 0.05, f"Unplugged USB_VBUS floated: {m_ped_open}"
    # In dual-powered mode, V_USB supplies R25+R26 sense divider (~200 uA forward), while USB->LDO power path is < 1 uA
    # and D+ pull-up is cleanly enabled (>= 3.1 V) for USB enumeration with zero reverse backfeed!
    assert abs(m_both["i_usb_pwr"]) < 1e-6, f"Dual-powered USB->LDO current >= 1uA: {m_both}"
    assert m_both["i_usb"] > 0.0, f"Dual-powered reverse current into USB host: {m_both}"
    assert m_both["v_dp_con"] >= 3.10, f"Dual-powered D+ pull-up failed to assert: {m_both}"
    assert m_both["v_ldo"] >= 4.60, f"Dual-powered VIN_3V3_LDO too low: {m_both}"
    assert abs(m_usb["i_buck"]) < 1e-6, f"USB->+5V_BUCK backfeed >= 1uA: {m_usb}"
    assert m_usb["v_buck"] < 0.05, f"USB-only back-power latch-up on +5V_BUCK: {m_usb}"
    assert m_usb["v_ldo"] >= 4.50, f"USB-only VIN_3V3_LDO too low for AMS1117: {m_usb}"
    assert m_usb["v_3v3"] >= 3.25, f"USB-only +3V3_DIG failed to come up: {m_usb}"

    # Dynamic transient verification of hot-unplug SUSPENDED PULLUP_EN=0 probe (>=50 us breaks SRV05-4 self-latch!)
    probe_deck = f"""* Beads Test 2C: Hot-Unplug SRV05-4 Latch-Break Probe (100 us PULLUP_EN=0)
.model D_SRV05 D(IS=2e-13 N=1.05 RS=0.8 CJO=50p)
.model SW_PU SW(RON=1.5k ROFF=1G VT=1.5 VH=0.1)
V_3V3 v3v3_dig 0 DC 3.30
* PULLUP_EN starts HIGH (self-latching unplugged USB_VBUS), drops LOW at t=20us for 100us probe
V_PU_EN pu_ctl 0 PWL(0 3.3 20u 3.3 21u 0 121u 0)
S_PU v3v3_dig usb_dp pu_ctl 0 SW_PU
R23 usb_dp usb_dp_con {r23}
D_SRV_DP_HI usb_dp_con usb_vbus D_SRV05
* Worst-case 300pF parasitic bus/TVS/diode capacitance on unplugged USB_VBUS
C_PAR usb_vbus 0 300p
R25 usb_vbus vbus_det {r25}
R26 vbus_det 0 {r26}
.tran 0.5u 120u
.control
run
meas tran vdet_latched FIND v(vbus_det) AT=18u
meas tran vdet_50us    FIND v(vbus_det) AT=71u
meas tran vdet_100us   FIND v(vbus_det) AT=119u
quit
.endc
.end
"""
    m_probe = run_ngspice("t2_unplug_probe", probe_deck)
    assert m_probe["vdet_latched"] > 1.40, f"Expected initial self-latched VBUS_DET > 1.4V: {m_probe}"
    assert m_probe["vdet_50us"] < 0.20, f"50us probe failed to discharge VBUS_DET below 0.20V: {m_probe}"
    assert m_probe["vdet_100us"] < 0.05, f"100us probe failed to discharge VBUS_DET below 0.05V: {m_probe}"

    # Dynamic transient verification of USB-only hot-plug ramp (0V -> 5.0V over 1ms) with +3V3_DIG + ESD + R77..80
    tran_deck = f"""* Beads Test 2B: USB-only Hot-Plug Transient Latch-Up Audit
.model PMOS_AO3401 PMOS(VTO=-1.1 KP=12 LAMBDA=0.02 RD=0.02 RS=0.02 IS=1e-13)
.model D_BODY D(IS=1e-12 N=1.05 RS=0.05)
.model D_1N5819 D(IS=2.0e-7 N=1.05 RS=0.12 BV=40 IBV=500u CJO=40p)
.model D_ESD D(IS=1e-13 N=1.05 RS=2.0)
V_USB usb_vbus 0 PWL(0 0 1m 5.0 15m 5.0)
R_BLEED v5_buck 0 {r3}
C_BUCK v5_buck 0 44u
D_USB_FWD usb_vbus usb_post D_1N5819
M_QUSB usb_post q_usb_g vin_3v3 vin_3v3 PMOS_AO3401 W=1 L=1
D_QUSB_BD usb_post vin_3v3 D_BODY
R27 v5_buck q_usb_g {r27}
D_OR_PED v5_buck vin_3v3 D_1N5819
C_LDO vin_3v3 0 10u
R_LDO_LOAD vin_3v3 0 94
B_3V3 v3v3_dig 0 V = 3.30 * (0.5 + 0.5 * tanh(20 * (v(vin_3v3) - 4.2)))
R77 v5_buck dac0_cs {r_cs_pu}
R78 v5_buck dac1_cs {r_cs_pu}
R79 v5_buck dac2_cs {r_cs_pu}
R80 v5_buck dac3_cs {r_cs_pu}
D_ESD0 dac0_cs v5_buck D_ESD
D_ESD1 dac1_cs v5_buck D_ESD
D_ESD2 dac2_cs v5_buck D_ESD
D_ESD3 dac3_cs v5_buck D_ESD
R_LVL_IN v3v3_dig 0 16Meg
.tran 20u 15m uic
.control
run
meas tran v_buck_pk MAX v(v5_buck) FROM=0m TO=15m
meas tran v_buck_ss AVG v(v5_buck) FROM=10m TO=15m
meas tran v_3v3_ss  AVG v(v3v3_dig) FROM=10m TO=15m
quit
.endc
.end
"""
    m_tran = run_ngspice("t2_usb_only_tran", tran_deck)
    assert m_tran["v_buck_pk"] < 0.10 and m_tran["v_buck_ss"] < 0.05, f"USB-only transient latch-up on +5V_BUCK: {m_tran}"
    assert m_tran["v_3v3_ss"] >= 3.25, f"USB-only transient +3V3_DIG failed: {m_tran}"
    print(
        f"[PASS] Test 2 (Bidirectional USB Isolation + SRV05-4 VBUS_DET Pull-Up Gating & Probe): "
        f"Pedal->0VHost={abs(m_ped['i_usb'])*1e9:.2f}nA (vs ungated {abs(m_ungated_0v['i_usb'])*1e3:.2f}mA) | "
        f"Unplugged VBUS={m_ped_open['v_vbus']*1e3:.2f}mV | "
        f"Probe(50us)={m_probe['vdet_50us']*1e3:.1f}mV (latched={m_probe['vdet_latched']:.2f}V) | "
        f"Both->Iusb_pwr={abs(m_both['i_usb_pwr'])*1e9:.2f}nA (D+={m_both['v_dp_con']:.2f}V) | "
        f"USB->5V_BUCK={abs(m_usb['i_buck'])*1e9:.1f}nA (Vbuck_pk={m_tran['v_buck_pk']*1e3:.2f}mV)"
    )


def test_3_photomos_popless_bypass(vals: dict[str, str]) -> None:
    r_out_ser = parse_value_ohms(vals["R65"])
    r_bleed = parse_value_ohms(vals["R39"])
    r_slew = parse_value_ohms(vals["R33"])
    c_slew = parse_cap_farads(vals["C32"])
    r_led = parse_value_ohms(vals["R31"])

    # Verify TLP172AM LED current from +3V3_DIG: (3.30 - 1.27) / R31 >= 5.0 mA
    i_led_ma = (3.30 - 1.27) / r_led * 1000.0
    assert i_led_ma >= 5.0, f"TLP172AM LED current {i_led_ma:.2f} mA < 5.0 mA min!"

    # Transient simulation of 15ms clickless bypass window with 3ms relay contact bounce chopping 1.0Vpp 440Hz audio
    deck = f"""* Beads Test 3: TLP172AM PhotoMOS Popless Mute Attenuation & Relay Bounce Spike
.model SW_PMOS SW(RON=1.0 ROFF=1G VT=1.5 VH=0.2)
.model SW_REL  SW(RON=0.05 ROFF=1G VT=2.5 VH=0.1)
* Live 1.0Vpp (0.5Vpk) 440Hz guitar signal on return stage behind R65 (220R)
V_SIG ret_src 0 SIN(0 0.5 440)
R_SER ret_src ret_no {r_out_ser}
* Soft-slewed PhotoMOS mute command: HIGH from t=5ms to t=16.5ms (11.5ms active inside 15ms window)
V_MUTE_GPIO mute_gpio 0 PULSE(0 3.3 5m 10u 10u 11.5m 50m)
R_SLEW mute_gpio mute_ctl {r_slew}
C_SLEW mute_ctl 0 {c_slew}
* Simulated G6K-2F-Y relay contact switching with 3 rapid contact bounces between t=8.5ms and t=11.5ms
V_REL_BOUNCE rel_ctl 0 PWL(0 5 8.5m 5 8.55m 0 9.0m 0 9.05m 5 9.6m 5 9.65m 0 10.2m 0 10.25m 5 10.8m 5 10.85m 0 25m 0)
S_REL ret_no gtr_out rel_ctl 0 SW_REL
S_MUTE gtr_out 0 mute_ctl 0 SW_PMOS
R_BLEED gtr_out 0 {r_bleed}
R_AMP_IN gtr_out 0 1Meg
.tran 5u 24m
.control
run
let vabs = abs(v(gtr_out))
meas tran vpk_unmuted MAX vabs FROM=1m TO=4.5m
meas tran vpk_muted   MAX vabs FROM=7.5m TO=8.4m
meas tran vpk_bounce  MAX vabs FROM=8.5m TO=12.0m
quit
.endc
.end
"""
    m = run_ngspice("t3_photomos", deck)
    atten_db = 20.0 * math.log10(m["vpk_unmuted"] / max(m["vpk_muted"], 1e-12))
    assert atten_db > 45.0, f"PhotoMOS attenuation {atten_db:.2f} dB <= 45 dB"
    # Verify at standard guitar 350mVpk (700mVpp) that bounce peak is strictly < 2.0 mV!
    deck_g = deck.replace("SIN(0 0.5 440)", "SIN(0 0.35 440)")
    mg = run_ngspice("t3_photomos_gtr", deck_g)
    atten_g_db = 20.0 * math.log10(mg["vpk_unmuted"] / max(mg["vpk_muted"], 1e-12))
    assert atten_g_db > 45.0, f"PhotoMOS attenuation {atten_g_db:.2f} dB <= 45 dB"
    assert mg["vpk_bounce"] < 2.0e-3, f"Guitar bounce spike {mg['vpk_bounce']*1e3:.3f} mV >= 2.0 mV"
    print(
        f"[PASS] Test 3 (TLP172AM PhotoMOS Popless Bypass): "
        f"I_LED={i_led_ma:.2f}mA | Atten={atten_g_db:.2f}dB (>45dB) | "
        f"BouncePeak={mg['vpk_bounce']*1e3:.3f}mV (<2.0mV)"
    )


def test_4_stereo_guitar_unity(vals: dict[str, str]) -> None:
    # Pull exact resistor & capacitor values from main_board.net
    c_in = parse_cap_farads(vals["C33"])
    r_rf = parse_value_ohms(vals["R43"])
    c_rf = parse_cap_farads(vals["C34"])
    r_bias = parse_value_ohms(vals["R44"])
    r_1a_f = parse_value_ohms(vals["R45"])
    r_1a_g = parse_value_ohms(vals["R46"])
    r_1b_f = parse_value_ohms(vals["R47"]) + parse_value_ohms(vals["R48"])
    c_1b_f = parse_cap_farads(vals["C35"])
    r_1b_g = parse_value_ohms(vals["R49"])
    r_send = parse_value_ohms(vals["R50"])
    r_ret_top = parse_value_ohms(vals["R59"])
    r_ret_bot = parse_value_ohms(vals["R60"]) + parse_value_ohms(vals["R61"])
    c_ret_ac = parse_cap_farads(vals["C39"])
    r_ret_bleed = parse_value_ohms(vals["R41"])
    r_out_ser = parse_value_ohms(vals["R65"])

    deck = f"""* Beads Test 4: End-to-End Guitar Preamp + Return Stage Unity Gain & 0 deg Phase at 12-o'clock
.subckt OPAMP_TL072 inp inn out
* Real TL072 macro: A_OL=100dB, GBW=3MHz (pole at 30Hz), Rout=50 Ohm
E_GAIN n1 0 inp inn 1e5
R_POLE n1 n2 1k
C_POLE n2 0 5.3u
E_BUF n3 0 n2 0 1.0
R_OUT n3 out 50
.ends
V_IN gtr_in 0 DC 0 AC 1 0
C_IN gtr_in pre_ac {c_in}
R_RF pre_ac pre_jfet {r_rf}
C_RF pre_jfet 0 {c_rf}
R_BIAS pre_jfet 0 {r_bias}
* Stage 1A: 2.0x non-inverting
X1A pre_jfet in1a_inv pre_send OPAMP_TL072
R1AF pre_send in1a_inv {r_1a_f}
R1AG in1a_inv 0 {r_1a_g}
* RV_IN_TRIM at exact 12-o'clock (50%: 5k top / 5k bottom)
R_INP_TOP pre_send in_wip 5k
R_INP_BOT in_wip 0 5k
* Stage 1B: 8.0x non-inverting -> 1k -> Beads 100k unity passthrough -> RET
X1B in_wip in1b_inv send_pre OPAMP_TL072
R1BF send_pre in1b_inv {r_1b_f}
C1BF send_pre in1b_inv {c_1b_f}
R1BG in1b_inv 0 {r_1b_g}
R_SEND send_pre send_jack {r_send}
R_BEADS_IN send_jack 0 100k
* Unity patch from SEND to RET (modeling Beads at 0dB dry)
E_BEADS ret_jack 0 send_jack 0 1.0
* Return stage: 75k / (24k+1k) = 0.250x -> NE5532 follower -> 50% RV_OUT_TRIM -> TL072 -> 10uF -> 220R
R_RT ret_jack ret_pad {r_ret_top}
R_RB ret_pad 0 {r_ret_bot}
X2A ret_pad pre_out pre_out OPAMP_TL072
R_OUTP_TOP pre_out out_wip 5k
R_OUTP_BOT out_wip 0 5k
X2B out_wip ret_buf ret_buf OPAMP_TL072
C_RET ret_buf ret_ac {c_ret_ac}
R_RBL ret_ac 0 {r_ret_bleed}
R_OS ret_ac gtr_out {r_out_ser}
R_AMP gtr_out 0 1Meg
.ac dec 50 1 200k
.control
run
let sdb = db(v(send_pre))
let odb = db(v(gtr_out))
let oph = ph(v(gtr_out))
meas ac send_mag_1k FIND sdb AT=1000
meas ac total_gain_db FIND odb AT=1000
meas ac total_phase_rad FIND oph AT=1000
meas ac lf_gain_20hz FIND odb AT=20
meas ac hf_gain_20khz FIND odb AT=20000
quit
.endc
.end
"""
    m = run_ngspice("t4_unity_audio", deck)
    total_phase_deg = m["total_phase_rad"] * 180.0 / math.pi
    assert abs(m["send_mag_1k"] - 18.06) < 0.25, f"Preamp gain off: {m['send_mag_1k']:.3f} dB"
    # Theoretical exact including 10k/1M RF stopper (-0.086dB) & 1k/100k Eurorack send protection (-0.086dB) = -0.177 dB
    assert abs(m["total_gain_db"]) < 0.25, f"End-to-end 12-o'clock gain not unity: {m['total_gain_db']:.3f} dB"
    assert abs(total_phase_deg) < 2.0, f"End-to-end phase inverted/shifted: {total_phase_deg:.2f} deg"
    assert m["lf_gain_20hz"] > -1.0, f"Bass rolloff at 20Hz too steep: {m['lf_gain_20hz']:.2f} dB"
    assert m["hf_gain_20khz"] > -1.0, f"Treble rolloff at 20kHz too steep: {m['hf_gain_20khz']:.2f} dB"
    print(
        f"[PASS] Test 4 (12-o'clock Stereo Unity & 0 deg Phase): "
        f"Send={m['send_mag_1k']:+.2f}dB | Total={m['total_gain_db']:+.3f}dB | "
        f"Phase={total_phase_deg:+.2f}deg | 20Hz={m['lf_gain_20hz']:+.2f}dB | 20kHz={m['hf_gain_20khz']:+.2f}dB"
    )


def test_5_bipolar_cv_dac(vals: dict[str, str]) -> None:
    rp1 = parse_value_ohms(vals["R81"])
    rp2 = parse_value_ohms(vals["R82"])
    rg = parse_value_ohms(vals["R83"])
    rfb = parse_value_ohms(vals["R84"])
    rout = parse_value_ohms(vals["R85"])

    out_v = {}
    for tag, vdac in [("min0", 0.0), ("mid2048", 2.048), ("max4095", 4.095)]:
        deck = f"""* Beads Test 5: Bipolar CV Output Stage ({tag}, Vdac={vdac}V)
.subckt OPAMP_BIP inp inn out
B1 out 0 V = max(min(1e5*(v(inp)-v(inn)), 10.8), -10.8)
.ends
V_REF vref 0 DC 2.495
V_DAC vdac 0 DC {vdac}
R_P1 vdac inp {rp1}
R_P2 inp 0 {rp2}
R_G vref inn {rg}
R_FB amp inn {rfb}
X_CV inp inn amp OPAMP_BIP
R_OUT amp cv_out {rout}
R_LOAD cv_out 0 100k
.op
.control
op
let v_amp = v(amp)
let v_cv = v(cv_out)
print v_amp v_cv
quit
.endc
.end
"""
        out_v[tag] = run_ngspice(f"t5_{tag}", deck)

    assert out_v["min0"]["v_cv"] <= -8.00 and out_v["min0"]["v_cv"] >= -8.50, f"CV min out of spec: {out_v['min0']}"
    assert abs(out_v["mid2048"]["v_cv"]) <= 0.05, f"CV mid not ~0V: {out_v['mid2048']}"
    assert out_v["max4095"]["v_cv"] >= 8.00 and out_v["max4095"]["v_cv"] <= 8.50, f"CV max out of spec: {out_v['max4095']}"
    print(
        f"[PASS] Test 5 (8-Ch Bipolar CV Stage): "
        f"code0={out_v['min0']['v_cv']:+.3f}V | code2048={out_v['mid2048']['v_cv']:+.3f}V | "
        f"code4095={out_v['max4095']['v_cv']:+.3f}V"
    )


def test_6_mcp6002_adc_clamp(vals: dict[str, str]) -> None:
    r_sl = parse_value_ohms(vals["R67"])
    r_sr = parse_value_ohms(vals["R68"])
    r_div = parse_value_ohms(vals["R69"])
    r_prot = parse_value_ohms(vals["R70"])
    r_damp = parse_value_ohms(vals["R71"])
    r_fb = parse_value_ohms(vals["R72"])
    r_g = parse_value_ohms(vals["R73"])
    c_pk = parse_cap_farads(vals["C41"])
    r_bleed = parse_value_ohms(vals["R74"])
    r_adc = parse_value_ohms(vals["R75"])
    c_adc = parse_cap_farads(vals["C42"])

    def sim_env(tag: str, vpk_l: float, vpk_r: float) -> dict[str, float]:
        deck = f"""* Beads Test 6: +3.3V MCP6002 Peak Detector & Fault Clamp ({tag}, L={vpk_l}Vpk, R={vpk_r}Vpk)
.model D_SIG D(IS=2.5e-9 N=1.75 RS=0.5)
.subckt MCP6002_3V3 inp inn out
* Smooth physical MCP6002 (1MHz GBW, 0.00V..3.30V rail-to-rail single supply, Rout=100 Ohm)
B_GAIN n1 0 V = 1.65 + 1.65 * tanh(1e4 * (v(inp) - v(inn)) / 1.65)
R_POLE n1 n2 1k
C_POLE n2 0 1.6n
E_BUF n3 0 n2 0 1.0
R_OUT n3 out 100
.ends
V_VDD vdd 0 DC 3.30
V_SIGL send_l 0 SIN(0 {vpk_l} 440)
V_SIGR send_r 0 SIN(0 {vpk_r} 440)
R_SL send_l env_sum {r_sl}
R_SR send_r env_sum {r_sr}
R_DIV env_sum 0 {r_div}
* BAV99 clamp: Pin 1=GND->Node, Pin 2=Node->+3V3
D_LO 0 env_sum D_SIG
D_HI env_sum vdd D_SIG
R_PROT env_sum env_inp {r_prot}
X_ENV1 env_inp env_fb rect_out MCP6002_3V3
R_DAMP rect_out env_damp {r_damp}
D_PK env_damp pk_hold D_SIG
R_FB pk_hold env_fb {r_fb}
R_G env_fb 0 {r_g}
C_PK pk_hold 0 {c_pk}
R_BL pk_hold 0 {r_bleed}
X_ENV2 pk_hold env_buf env_buf MCP6002_3V3
R_ADC env_buf adc0 {r_adc}
C_ADC adc0 0 {c_adc}
.tran 20u 25m
.control
run
meas tran v_adc_max MAX v(adc0) FROM=5m TO=25m
meas tran v_adc_min MIN v(adc0) FROM=5m TO=25m
print v_adc_max v_adc_min
quit
.endc
.end
"""
        return run_ngspice(f"t6_{tag}", deck)

    m_mono = sim_env("mono_4vpk", 4.0, 0.0)
    m_stereo = sim_env("stereo_4vpk", 4.0, 4.0)
    m_fault = sim_env("fault_12vpk", 12.0, 12.0)
    assert 2.15 <= m_mono["v_adc_max"] <= 3.10, f"Mono 4Vpk on SEND_L failed to trip 2.10V PEAK threshold: {m_mono}"
    assert 2.15 <= m_stereo["v_adc_max"] <= 3.15, f"Stereo 4Vpk guitar envelope out of range: {m_stereo}"
    assert m_fault["v_adc_max"] <= 3.301, f"Fault 12Vpk exceeded +3.30V RP2040 ADC limit: {m_fault}"
    assert m_fault["v_adc_min"] >= -0.01, f"Fault 12Vpk went negative on RP2040 ADC: {m_fault}"
    print(
        f"[PASS] Test 6 (+3.3V MCP6002 Peak Detector & ADC Clamp): "
        f"Mono4Vpk->ADC={m_mono['v_adc_max']:.3f}V (>2.10V) | "
        f"Stereo4Vpk->ADC={m_stereo['v_adc_max']:.3f}V | "
        f"Fault12Vpk->ADC=[{m_fault['v_adc_min']:.3f}V, {m_fault['v_adc_max']:.3f}V] (<=3.30V)"
    )


def test_7_regulator_setpoints_and_esr(vals: dict[str, str], pin_nets: dict[tuple[str, str], str]) -> None:
    # Verify netlist feedback dividers for TPS5430 (+5.08V), TPS65131 (+14.65V/-14.56V, PSP/PSN=GND, I_VREF<=10uA),
    # LM317 (+12.0V), 79M12 ESR damping, VBUS_DET <= 3.30V @ 5.25V, and CJ431 capacitive isolation!
    r_buck_top = parse_value_ohms(vals["R4"]) + parse_value_ohms(vals["R5"]) + parse_value_ohms(vals["R6"])
    r_buck_bot = parse_value_ohms(vals["R7"])
    v_buck = 1.221 * (1.0 + r_buck_top / r_buck_bot)
    assert 4.95 <= v_buck <= 5.18, f"TPS5430 Vout {v_buck:.3f}V out of +5.05V +-2%"

    # TI SLVS493E: PSP (Pin 9) & PSN (Pin 11) MUST tie to GND (0V = fixed-frequency PWM)
    assert pin_nets[("U_PMIC", "9")] == "GND", f"U_PMIC.9 (PSP) must tie to GND, got {pin_nets[('U_PMIC', '9')]}"
    assert pin_nets[("U_PMIC", "11")] == "GND", f"U_PMIC.11 (PSN) must tie to GND, got {pin_nets[('U_PMIC', '11')]}"

    r_fbp_top = parse_value_ohms(vals["R12"]) + parse_value_ohms(vals["R13"])
    r_fbp_bot = parse_value_ohms(vals["R14"])
    v_pos_raw = 1.213 * (1.0 + r_fbp_top / r_fbp_bot)
    assert 14.35 <= v_pos_raw <= 14.95, f"TPS65131 +Vraw {v_pos_raw:.3f}V out of +14.65V headroom window"

    r_fbn_top = parse_value_ohms(vals["R15"]) + parse_value_ohms(vals["R16"])
    r_fbn_bot = parse_value_ohms(vals["R17"])
    i_vref_ua = 1.213 / r_fbn_bot * 1e6
    assert r_fbn_bot >= 120e3 and i_vref_ua <= 10.0, f"TPS65131 VREF load {i_vref_ua:.2f} uA > 10 uA max (R17={r_fbn_bot})"
    v_neg_raw = -1.213 * (r_fbn_top / r_fbn_bot)
    assert -14.95 <= v_neg_raw <= -14.25, f"TPS65131 -Vraw {v_neg_raw:.3f}V out of -14.55V headroom window"

    r_lm1 = parse_value_ohms(vals["R18"])
    r_lm2 = parse_value_ohms(vals["R19"]) + parse_value_ohms(vals["R20"])
    v_p12 = 1.25 * (1.0 + r_lm2 / r_lm1) + 50e-6 * r_lm2
    assert 11.80 <= v_p12 <= 12.20, f"LM317 +12V_EUR {v_p12:.3f}V out of +-2%"
    assert (v_pos_raw - v_p12) >= 2.20, f"LM317 dropout headroom {v_pos_raw - v_p12:.2f}V < 2.20V"
    assert (abs(v_neg_raw) - 12.00) >= 2.20, f"79M12 dropout headroom {abs(v_neg_raw) - 12.0:.2f}V < 2.20V"

    # VBUS_DET divider <= 3.30V at 5.25V USB max & >= 2.50V at 4.50V USB min
    r25 = parse_value_ohms(vals["R25"])
    r26 = parse_value_ohms(vals["R26"])
    vbus_det_max = 5.25 * r26 / (r25 + r26)
    vbus_det_min = 4.50 * r26 / (r25 + r26)
    assert vbus_det_max <= 3.30 and vbus_det_min >= 2.50, f"VBUS_DET range [{vbus_det_min:.3f}V, {vbus_det_max:.3f}V] out of spec"

    # CJ431 (U_REF) stability: C52 must NOT sit directly on VREF_RAW; isolated via R143 >= 200R
    assert pin_nets[("U_REF", "2")] == "VREF_RAW"
    assert pin_nets[("C52", "1")] == "VREF_FILT" and pin_nets[("C52", "1")] != pin_nets[("U_REF", "2")]
    r_iso = parse_value_ohms(vals["R143"])
    assert r_iso >= 200.0, f"CJ431 filter isolation resistor R143={r_iso} Ohm < 200 Ohm"

    r_esr = parse_value_ohms(vals["R_ESR_N12"])
    c_n12_bulk = parse_cap_farads(vals["C20"])
    c_n12_hf = parse_cap_farads(vals["C21"])
    assert 0.2 <= r_esr <= 1.0 and c_n12_bulk >= 9.9e-6 and c_n12_hf >= 0.99e-6, "79M12 ESR damping network invalid"
    print(
        f"[PASS] Test 7 (Netlist Power Setpoints, PSP/PSN=GND, VREF, VBUS_DET & CJ431): "
        f"+5V_BUCK={v_buck:.3f}V | +Vraw={v_pos_raw:+.2f}V | -Vraw={v_neg_raw:+.2f}V (Ivref={i_vref_ua:.2f}uA) | "
        f"VBUS_DET@5.25V={vbus_det_max:.3f}V | CJ431_Riso={r_iso:.0f}R | 79M12 ESR={r_esr:.2f}R"
    )


def main() -> int:
    vals = load_netlist_values()
    pin_nets = load_netlist_pin_nets()
    test_1_rpp_and_gate_clamp(vals)
    test_2_usb_isolation(vals, pin_nets)
    test_3_photomos_popless_bypass(vals)
    test_4_stereo_guitar_unity(vals)
    test_5_bipolar_cv_dac(vals)
    test_6_mcp6002_adc_clamp(vals)
    test_7_regulator_setpoints_and_esr(vals, pin_nets)
    print("ALL 7 NGSPICE ANALOG, POWER, USB-ISOLATION & POPLESS-BYPASS GATES PASSED!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
