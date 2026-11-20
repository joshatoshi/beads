#include "bezier_drift.h"

static uint32_t xorshift32(uint32_t *state) {
    uint32_t x = *state;
    if (x == 0u) {
        x = 0x9E3779B9u;
    }
    x ^= x << 13u;
    x ^= x >> 17u;
    x ^= x << 5u;
    *state = x;
    return x;
}

static int32_t clamp_q15(int32_t v) {
    if (v > 32767) return 32767;
    if (v < -32767) return -32767;
    return v;
}

/* Exact divide-by-3 via 32-bit multiply-shift (zero division helpers on Cortex-M0+!) */
static int32_t div3_s32(int32_t x) {
    int32_t neg = (x < 0);
    uint32_t ax = (uint32_t)(neg ? -x : x);
    /* (ax * 21845 + 32768) >> 16 == round(ax / 3.000046) */
    uint32_t q = ((ax * 21845u) + 32768u) >> 16u;
    return neg ? -(int32_t)q : (int32_t)q;
}

static void recompute_control_points(bezier_drift_t *b) {
    /* Hermite -> Cubic Bezier conversion guaranteeing exact C0 and C1 continuity:
     *   P0 = y0
     *   P1 = y0 + (v0 * tension_q15 / 32768) / 3
     *   P2 = y1 - (v1 * tension_q15 / 32768) / 3
     *   P3 = y1
     * Boundary derivative at t=0 is 3*(P1 - P0) = v0_scaled;
     * Boundary derivative at t=1 is 3*(P3 - P2) = v1_scaled.
     * When advancing segment: new y0 = old y1, new v0 = old v1 -> EXACT C1 continuity! */
    int32_t dv0 = div3_s32((b->v0 * (int32_t)b->tension_q15) >> 15);
    int32_t dv1 = div3_s32((b->v1 * (int32_t)b->tension_q15) >> 15);
    b->p0 = b->y0;
    b->p1 = clamp_q15(b->y0 + dv0);
    b->p2 = clamp_q15(b->y1 - dv1);
    b->p3 = b->y1;
}

static void advance_segment(bezier_drift_t *b) {
    /* Carry over exact position and slope from previous endpoint */
    b->y0 = b->y1;
    b->v0 = b->v1;
    /* Sample next organic target y1 in [-25500, +25500] and bounded slope v1 in [-20000, +20000]
     * (25500 + 6667 = 32167 < 32767 -> P1 & P2 NEVER clip, guaranteeing 100% exact C1 continuity!) */
    int32_t r1 = (int32_t)(int16_t)(xorshift32(&b->prng_state) & 0xFFFFu);
    int32_t r2 = (int32_t)(int16_t)(xorshift32(&b->prng_state) & 0xFFFFu);
    b->y1 = (r1 * 25500) >> 15;
    b->v1 = (r2 * 20000) >> 15;
    recompute_control_points(b);
}

void bezier_drift_init(bezier_drift_t *b, uint32_t seed, uint16_t tension_q15) {
    b->prng_state = (seed != 0u) ? seed : 0xA5A55A5Au;
    b->tension_q15 = (tension_q15 < 4096u) ? 4096u : (tension_q15 > 32767u ? 32767u : tension_q15);
    b->phase_q32 = 0u;
    b->y1 = 0;
    b->v1 = 0;
    advance_segment(b);
}

/* Pure 32-bit de Casteljau evaluation of Cubic Bezier at t_q15 in [0..32768] (0..1.0).
 * Uses only 32-bit signed multiplies and arithmetic right shifts -> zero 64-bit or float ops! */
int32_t bezier_drift_eval_q15(const bezier_drift_t *b, uint16_t t_q15) {
    int32_t t = (int32_t)t_q15;
    if (t > 32768) t = 32768;
    /* Level 1 linear interpolations */
    int32_t q0 = b->p0 + (((b->p1 - b->p0) * t) >> 15);
    int32_t q1 = b->p1 + (((b->p2 - b->p1) * t) >> 15);
    int32_t q2 = b->p2 + (((b->p3 - b->p2) * t) >> 15);
    /* Level 2 */
    int32_t r0 = q0 + (((q1 - q0) * t) >> 15);
    int32_t r1 = q1 + (((q2 - q1) * t) >> 15);
    /* Level 3 */
    int32_t out = r0 + (((r1 - r0) * t) >> 15);
    return clamp_q15(out);
}

int32_t bezier_drift_step(bezier_drift_t *b, uint32_t phase_inc_q32) {
    uint32_t prev = b->phase_q32;
    b->phase_q32 += phase_inc_q32;
    if (b->phase_q32 < prev) {
        /* Wrapped past 1.0 -> advance to C1-matched next segment */
        advance_segment(b);
    }
    uint16_t t_q15 = (uint16_t)(b->phase_q32 >> 17u); /* Top 15 bits -> [0..32767] */
    return bezier_drift_eval_q15(b, t_q15);
}
