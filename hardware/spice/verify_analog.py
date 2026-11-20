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


def test_2_usb_isolation(vals: dict[str, str]) -> None:
    r27 = parse_value_ohms(vals["R27"])
    r28 = parse_value_ohms(vals["R28"])
    r3 = parse_value_ohms(vals["R3"])

    def sim_mode(tag: str, v_buck_src: float | None, v_usb_src: float | None) -> dict[str, float]:
        buck_elem = (
            f"V_BUCK v5_buck 0 DC {v_buck_src}"
            if v_buck_src is not None
            else f"V_BUCK_SENSE v5_buck v5_bleed DC 0\nR_BLEED v5_bleed 0 {r3}"
        )
        usb_elem = (
            f"V_USB usb_vbus 0 DC {v_usb_src}"
            if v_usb_src is not None
            else "V_USB usb_vbus 0 DC 0"
        )
        i_buck_expr = "-i(V_BUCK)" if v_buck_src is not None else "i(V_BUCK_SENSE)"
        deck = f"""* Beads Test 2: Bidirectional <1uA USB-C VBUS <-> +5V_BUCK Isolation ({tag})
.model PMOS_AO3401 PMOS(VTO=-1.1 KP=12 LAMBDA=0.02 RD=0.02 RS=0.02 IS=1e-13)
.model NMOS_AO3400 NMOS(VTO=1.0 KP=14 LAMBDA=0.02 RD=0.02 RS=0.02 IS=1e-13)
.model D_BODY D(IS=1e-12 N=1.05 RS=0.05)
.model D_1N5819 D(IS=2e-6 N=1.05 RS=0.12)
{buck_elem}
{usb_elem}
* USB path: D_USB_FWD (1N5819WS) + Q_USB (AO3401A: D=usb_post, S=vin_3v3, G=R27->+5V_BUCK)
D_USB_FWD usb_vbus usb_post D_1N5819
M_QUSB usb_post q_usb_g vin_3v3 vin_3v3 PMOS_AO3401 W=1 L=1
D_QUSB_BD usb_post vin_3v3 D_BODY
R27 v5_buck q_usb_g {r27}
* Pedal path: Q_PED_OR (AO3401A: D=+5V_BUCK, S=vin_3v3, G=q_ped_g) driven by Q_PED_DRV (AO3400A)
M_QPED v5_buck q_ped_g vin_3v3 vin_3v3 PMOS_AO3401 W=1 L=1
D_QPED_BD v5_buck vin_3v3 D_BODY
R28 vin_3v3 q_ped_g {r28}
M_QDRV q_ped_g v5_buck 0 0 NMOS_AO3400 W=1 L=1
* 50mA LDO load on VIN_3V3_LDO
R_LDO_LOAD vin_3v3 0 94
.op
.control
op
let v_ldo = v(vin_3v3)
let i_usb = -i(V_USB)
let i_buck = {i_buck_expr}
let v_buck = v(v5_buck)
print v_ldo i_usb i_buck v_buck
quit
.endc
.end
"""
        return run_ngspice(f"t2_{tag}", deck)

    m_ped = sim_mode("pedal_only", 5.08, None)      # Pedal ON, USB host powered off (0V)
    m_both = sim_mode("both_on", 5.08, 5.00)        # Both Pedal 5.08V and USB 5.00V ON
    m_usb = sim_mode("usb_only", None, 5.00)        # Pedal OFF (bleed to 0V), USB 5.00V ON

    assert abs(m_ped["i_usb"]) < 1e-6, f"Pedal->USB backfeed >= 1uA: {m_ped}"
    assert m_ped["v_ldo"] >= 5.00, f"Pedal-only VIN_3V3_LDO too low: {m_ped}"
    assert abs(m_both["i_usb"]) < 1e-6, f"Dual-powered USB current >= 1uA: {m_both}"
    assert m_both["v_ldo"] >= 5.00, f"Dual-powered VIN_3V3_LDO too low: {m_both}"
    assert abs(m_usb["i_buck"]) < 1e-6, f"USB->+5V_BUCK backfeed >= 1uA: {m_usb}"
    assert m_usb["v_ldo"] >= 4.50, f"USB-only VIN_3V3_LDO too low for AMS1117: {m_usb}"
    print(
        f"[PASS] Test 2 (Bidirectional USB Isolation): "
        f"Pedal->USB={abs(m_ped['i_usb'])*1e9:.2f}nA (Vldo={m_ped['v_ldo']:.3f}V) | "
        f"Both->Iusb={abs(m_both['i_usb'])*1e9:.2f}nA | "
        f"USB->5V_BUCK={abs(m_usb['i_buck'])*1e9:.2f}nA (Vldo={m_usb['v_ldo']:.3f}V)"
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

    def sim_env(tag: str, vpk_in: float) -> dict[str, float]:
        deck = f"""* Beads Test 6: +3.3V MCP6002 Peak Detector & Fault Clamp ({tag}, Vpk={vpk_in}V)
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
V_SIGL send_l 0 SIN(0 {vpk_in} 440)
V_SIGR send_r 0 SIN(0 {vpk_in} 440)
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

    m_norm = sim_env("normal_4vpk", 4.0)
    m_fault = sim_env("fault_12vpk", 12.0)
    assert 1.5 <= m_norm["v_adc_max"] <= 3.1, f"Normal 4Vpk guitar envelope out of range: {m_norm}"
    assert m_fault["v_adc_max"] <= 3.301, f"Fault 12Vpk exceeded +3.30V RP2040 ADC limit: {m_fault}"
    assert m_fault["v_adc_min"] >= -0.01, f"Fault 12Vpk went negative on RP2040 ADC: {m_fault}"
    print(
        f"[PASS] Test 6 (+3.3V MCP6002 Peak Detector & ADC Clamp): "
        f"Normal4Vpk->ADC={m_norm['v_adc_max']:.3f}V | "
        f"Fault12Vpk->ADC=[{m_fault['v_adc_min']:.3f}V, {m_fault['v_adc_max']:.3f}V] (<=3.30V)"
    )


def test_7_regulator_setpoints_and_esr(vals: dict[str, str]) -> None:
    # Verify netlist feedback dividers for TPS5430 (+5.08V), TPS65131 (+13.9V/-13.7V), LM317 (+12.0V), and 79M12 ESR damping!
    r_buck_top = parse_value_ohms(vals["R4"]) + parse_value_ohms(vals["R5"]) + parse_value_ohms(vals["R6"])
    r_buck_bot = parse_value_ohms(vals["R7"])
    v_buck = 1.221 * (1.0 + r_buck_top / r_buck_bot)
    assert 4.95 <= v_buck <= 5.18, f"TPS5430 Vout {v_buck:.3f}V out of +5.05V +-2%"

    r_fbp_top = parse_value_ohms(vals["R12"]) + parse_value_ohms(vals["R13"])
    r_fbp_bot = parse_value_ohms(vals["R14"])
    v_pos_raw = 1.213 * (1.0 + r_fbp_top / r_fbp_bot)
    assert 13.6 <= v_pos_raw <= 14.2, f"TPS65131 +Vraw {v_pos_raw:.3f}V out of range"

    r_fbn_top = parse_value_ohms(vals["R15"]) + parse_value_ohms(vals["R16"])
    r_fbn_bot = parse_value_ohms(vals["R17"])
    v_neg_raw = -1.213 * (r_fbn_top / r_fbn_bot)
    assert -14.1 <= v_neg_raw <= -13.4, f"TPS65131 -Vraw {v_neg_raw:.3f}V out of range"

    r_lm1 = parse_value_ohms(vals["R18"])
    r_lm2 = parse_value_ohms(vals["R19"]) + parse_value_ohms(vals["R20"])
    v_p12 = 1.25 * (1.0 + r_lm2 / r_lm1) + 50e-6 * r_lm2
    assert 11.80 <= v_p12 <= 12.20, f"LM317 +12V_EUR {v_p12:.3f}V out of +-2%"

    r_esr = parse_value_ohms(vals["R_ESR_N12"])
    c_n12_bulk = parse_cap_farads(vals["C20"])
    c_n12_hf = parse_cap_farads(vals["C21"])
    assert 0.2 <= r_esr <= 1.0 and c_n12_bulk >= 9.9e-6 and c_n12_hf >= 0.99e-6, "79M12 ESR damping network invalid"
    print(
        f"[PASS] Test 7 (Netlist Power Setpoints & 79M12 ESR): "
        f"+5V_BUCK={v_buck:.3f}V | +Vraw={v_pos_raw:.2f}V | -Vraw={v_neg_raw:.2f}V | "
        f"+12V_EUR={v_p12:.3f}V | 79M12 ESR={r_esr:.2f}R + {c_n12_bulk*1e6:.0f}uF || {c_n12_hf*1e6:.0f}uF"
    )


def main() -> int:
    vals = load_netlist_values()
    test_1_rpp_and_gate_clamp(vals)
    test_2_usb_isolation(vals)
    test_3_photomos_popless_bypass(vals)
    test_4_stereo_guitar_unity(vals)
    test_5_bipolar_cv_dac(vals)
    test_6_mcp6002_adc_clamp(vals)
    test_7_regulator_setpoints_and_esr(vals)
    print("ALL 7 NGSPICE ANALOG, POWER, USB-ISOLATION & POPLESS-BYPASS GATES PASSED!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
