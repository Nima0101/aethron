// SPDX-License-Identifier: GPL-3.0-only
#include "../aethron_raster_native/kernel.hpp"
#include <array>
#include <limits>

int main() {
    aethron::Brown c{7,1,7,1,0,3,1,{2,1,0,0,1,1,0,0,3,0.5,0,0,0,0}};
    std::array<std::uint8_t,7> source{0,1,2,3,4,5,6};
    std::array<std::uint8_t,3> data{},mask{};
    if (!aethron::remap(c,source,data,mask) || data != std::array<std::uint8_t,3>{0,3,0} ||
        mask != std::array<std::uint8_t,3>{1,1,0}) return 1;
    for (int i=0; i<14; ++i) {
        auto bad=c; bad.p[i]=std::numeric_limits<double>::quiet_NaN();
        if (aethron::remap(bad,source,data,mask)) return 2;
    }
    for (int invalid : {-2147483647,-1,0,8193,2147483647}) {
        auto bad=c; bad.step=invalid;
        if (aethron::remap(bad,source,data,mask)) return 3;
    }
    for (int n=0; n<7; ++n)
        if (aethron::remap(c,std::span(source).first(n),data,mask)) return 4;
    if (aethron::remap(c,source,std::span(data).first(2),mask)) return 5;
    auto outside=c; outside.p[8]=4;
    if (aethron::remap(outside,source,data,mask)) return 6;
    // Deterministic malformed-dimension probe under ASan/UBSan; buffers stay tiny.
    std::uint32_t seed=20261009;
    for (int i=0;i<10000;++i) {
        seed=seed*1664525u+1013904223u;
        auto bad=c; bad.width=static_cast<int>(seed & 0x7fffffffu);
        bad.out_height=static_cast<int>((seed>>10)&0x1fffffu);
        (void)aethron::remap(bad,source,data,mask);
    }
}
