/* Original bounded audit driver; generated MAVLink headers stay in build output.
 * SPDX-License-Identifier: GPL-3.0-only. No socket, sender, or production entry. */
#define _POSIX_C_SOURCE 200809L
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include "subset/mavlink.h"
#include "vectors.h"

typedef struct { int accepted; unsigned message; uint32_t boot; float values[6]; } result;

static result decode(const uint8_t *p, size_t n) {
    result out = {0};
    if (n < 12 || n > 280 || p[0] != 253 || p[2] || p[3] ||
        p[5] != 1 || p[6] != 1 || p[1] < 1 || p[1] > 28 || n != p[1] + 12u)
        return out;
    unsigned id = p[7] | ((unsigned)p[8] << 8) | ((unsigned)p[9] << 16);
    if (id != 30 && id != 32) return out;
    mavlink_message_t rx = {0}, msg = {0};
    mavlink_status_t status = {0}, returned = {0};
    uint8_t framing = 0;
    for (size_t i = 0; i < n; i++)
        framing = mavlink_frame_char_buffer(&rx, &status, p[i], &msg, &returned);
    if (framing != MAVLINK_FRAMING_OK || msg.msgid != id) return out;
    if (id == 30) {
        mavlink_attitude_t value;
        mavlink_msg_attitude_decode(&msg, &value);
        out.boot = value.time_boot_ms;
        float values[] = {value.roll, value.pitch, value.yaw,
                          value.rollspeed, value.pitchspeed, value.yawspeed};
        for (int i = 0; i < 6; i++) out.values[i] = values[i];
    } else {
        mavlink_local_position_ned_t value;
        mavlink_msg_local_position_ned_decode(&msg, &value);
        out.boot = value.time_boot_ms;
        float values[] = {value.x, value.y, value.z, value.vx, value.vy, value.vz};
        for (int i = 0; i < 6; i++) out.values[i] = values[i];
    }
    for (int i = 0; i < 6; i++) if (!isfinite(out.values[i])) return (result){0};
    out.message = id;
    out.accepted = 1;
    return out;
}

static uint64_t now(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) exit(2);
    return (uint64_t)t.tv_sec * 1000000000u + (uint64_t)t.tv_nsec;
}

static int compare(const void *a, const void *b) {
    uint64_t x = *(const uint64_t *)a, y = *(const uint64_t *)b;
    return (x > y) - (x < y);
}

int main(void) {
    printf("{\"results\":[");
    for (size_t i = 0; i < VECTOR_COUNT; i++) {
        result r = decode(vectors[i], lengths[i]);
        if (i) printf(",");
        if (!r.accepted) printf("{\"accepted\":false}");
        else {
            printf("{\"accepted\":true,\"message\":%u,\"boot\":%u,\"values\":[",
                   r.message, r.boot);
            for (int j = 0; j < 6; j++) printf("%s%.9g", j ? "," : "", (double)r.values[j]);
            printf("]}");
        }
    }
    uint64_t elapsed[512];
    volatile unsigned accepted = 0;
    for (size_t i = 0; i < 512; i++) {
        size_t k = i % VECTOR_COUNT;
        uint64_t start = now();
        result r = decode(vectors[k], lengths[k]);
        elapsed[i] = now() - start;
        accepted += (unsigned)r.accepted;
    }
    qsort(elapsed, 512, sizeof(*elapsed), compare);
    printf("],\"benchmark\":{\"samples\":512,\"accepted\":%u,\"p50_ns\":%llu,"
           "\"p95_ns\":%llu,\"max_ns\":%llu}}\n", accepted,
           (unsigned long long)elapsed[255], (unsigned long long)elapsed[486],
           (unsigned long long)elapsed[511]);
    return 0;
}
