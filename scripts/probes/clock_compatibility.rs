// SPDX-License-Identifier: GPL-3.0-only
// Comparison probe only; not linked into the appliance.
// rustc --edition=2021 --crate-type cdylib -O -D warnings clock_compatibility.rs -o LIBRARY
#[no_mangle]
pub extern "C" fn compatible(a: u64, ae: u64, b: u64, be: u64) -> u8 {
    u8::from(
        a.abs_diff(b)
            .checked_add(ae)
            .and_then(|sum| sum.checked_add(be))
            .is_some_and(|sum| sum <= 50_000_000),
    )
}

#[test]
fn boundary_and_overflow() {
    assert_eq!(compatible(0, 4_000_000, 40_000_000, 6_000_000), 1);
    assert_eq!(compatible(0, 4_000_001, 40_000_000, 6_000_000), 0);
    assert_eq!(compatible(u64::MAX, 0, u64::MAX, 0), 1);
    assert_eq!(compatible(0, 1, u64::MAX, 0), 0);
    assert_eq!(compatible(0, u64::MAX, 0, u64::MAX), 0);
}
