#include <stddef.h>
void pack(const unsigned char *restrict source, float *restrict output) {
    for (size_t channel = 0; channel < 3; ++channel)
        for (size_t pixel = 0; pixel < 640 * 640; ++pixel)
            output[channel * 640 * 640 + pixel] = source[pixel * 3 + channel];
}
