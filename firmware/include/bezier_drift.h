#ifndef BEADS_BEZIER_DRIFT_H
#define BEADS_BEZIER_DRIFT_H

#include <stdint.h>

/* Piecewise C1-continuous Cubic Bezier Random Drift Generator (pure 32-bit fixed point!).
 * Output range: signed Q15 [-32767 .. +32767].
 * Continuity guarantee across segment boundaries:
 *   y(1) of segment k == y(0) of segment k+1  (C0 position continuity)
 *   dy/dt(1) of segment k == dy/dt(0) of segment k+1  (C1 velocity continuity)
 * Achieved by matching P1 = y0 + (v0 * tension)/3 and P2 = y1 - (v1 * tension)/3!
 */
typedef struct {
    int32_t  y0;          /* Segment start value Q15 [-32767..+32767] */
    int32_t  y1;          /* Segment end value Q15 [-32767..+32767] */
    int32_t  v0;          /* Segment start slope Q15 */
    int32_t  v1;          /* Segment end slope Q15 */
    int32_t  p0, p1, p2, p3; /* Cubic Bezier control points Q15 */
    uint32_t phase_q32;   /* Segment parameter t in [0, 2^32 - 1] */
    uint32_t prng_state;  /* xorshift32 deterministic state */
    uint16_t tension_q15; /* Smoothness/tension scaling [4096..32767], default 24576 (0.75) */
} bezier_drift_t;

void    bezier_drift_init(bezier_drift_t *b, uint32_t seed, uint16_t tension_q15);
int32_t bezier_drift_eval_q15(const bezier_drift_t *b, uint16_t t_q15);
int32_t bezier_drift_step(bezier_drift_t *b, uint32_t phase_inc_q32);

#endif /* BEADS_BEZIER_DRIFT_H */
