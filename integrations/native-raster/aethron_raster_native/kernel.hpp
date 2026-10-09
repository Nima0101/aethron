// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <span>

namespace aethron {
struct Brown {
    int width, height, step, bytes, big, out_width, out_height;
    // source fx/fy/cx/cy, output fx/fy/cx/cy, radius, k1/k2/p1/p2/k3
    std::array<double, 14> p;
};

inline bool remap(const Brown& c, std::span<const std::uint8_t> source,
                  std::span<std::uint8_t> data, std::span<std::uint8_t> mask) noexcept {
    if (c.width < 1 || c.width > 1920 || c.height < 1 || c.height > 1080 ||
        (c.bytes != 1 && c.bytes != 2) || (c.big != 0 && c.big != 1) ||
        c.step < c.width*c.bytes || c.step > 8192 || c.out_width < 1 ||
        c.out_width > 1920 || c.out_height < 1 || c.out_height > 1080) return false;
    const auto pixels = static_cast<std::size_t>(c.out_width)*c.out_height;
    if (pixels > 640*512 || source.size() != static_cast<std::size_t>(c.step)*c.height ||
        source.size() > 8*1024*1024 || data.size() != pixels*c.bytes || mask.size() != pixels)
        return false;
    const auto& p = c.p;
    for (double v : p) if (!std::isfinite(v)) return false;
    if (p[0] < 1e-6 || p[1] < 1e-6 || p[4] < 1e-6 || p[5] < 1e-6 ||
        p[8] <= 0 || p[8] > 3 ||
        p[2] < -2*c.width || p[2] > 3*c.width || p[3] < -2*c.height || p[3] > 3*c.height ||
        p[6] < -2*c.out_width || p[6] > 3*c.out_width || p[7] < -2*c.out_height || p[7] > 3*c.out_height)
        return false;
    for (int i=9; i<14; ++i) if (std::abs(p[i]) > 2) return false;
    // Lens invertibility is checked by the unchanged Python reference validator.
    // This internal kernel independently checks memory/numeric bounds, not admission.
    std::fill(data.begin(),data.end(),0);
    std::fill(mask.begin(),mask.end(),0);
    const bool identity = c.width==c.out_width && c.height==c.out_height &&
        p[0]==p[4] && p[1]==p[5] && p[2]==p[6] && p[3]==p[7] &&
        p[9]==0 && p[10]==0 && p[11]==0 && p[12]==0 && p[13]==0;
    for (int row=0; row<c.out_height; ++row) {
        const double y=(row-p[7])/p[5];
        for (int col=0; col<c.out_width; ++col) {
            const double x=(col-p[6])/p[4], r2=x*x+y*y;
            if (r2 > std::pow(p[8],2)) continue;
            const double scale=1+p[9]*r2+p[10]*std::pow(r2,2)+p[13]*std::pow(r2,3);
            const double xd=x*scale+2*p[11]*x*y+p[12]*(r2+2*x*x);
            const double yd=y*scale+p[11]*(r2+2*y*y)+2*p[12]*x*y;
            const double u=identity ? col : p[0]*xd+p[2], v=identity ? row : p[1]*yd+p[3];
            if (!(u>=0 && u<=c.width-1 && v>=0 && v<=c.height-1)) continue;
            const auto sx=static_cast<std::size_t>(std::floor(u+0.5));
            const auto sy=static_cast<std::size_t>(std::floor(v+0.5));
            const auto index=static_cast<std::size_t>(row)*c.out_width+col;
            const auto offset=sy*c.step+sx*c.bytes;
            for (int b=0; b<c.bytes; ++b)
                data[index*c.bytes+b]=source[offset+(c.big ? c.bytes-1-b : b)];
            mask[index]=1;
        }
    }
    return true;
}
}
