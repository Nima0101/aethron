// Audit-only bounded input shared with the Python reference. No transport API.
use super::Step;
use std::io::{self, Read};

const LIMIT: usize = 65536;

pub struct Case<'a> {
    pub system: u8,
    pub component: u8,
    pub steps: Vec<Step<'a>>,
}

pub fn read<R: Read>(mut input: R) -> io::Result<Vec<u8>> {
    let mut raw = vec![0; LIMIT + 1];
    let mut used = 0;
    loop {
        match input.read(&mut raw[used..]) {
            Ok(0) => { raw.truncate(used); return Ok(raw); }
            Ok(size) => {
                used += size;
                if used > LIMIT {
                    return Err(io::Error::new(io::ErrorKind::InvalidData, "audit_input_too_large"));
                }
            }
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            Err(error) => return Err(error),
        }
    }
}

fn take<'a>(raw: &mut &'a [u8], length: usize) -> Result<&'a [u8], &'static str> {
    if length > raw.len() { return Err("audit_input_truncated"); }
    let (value, remaining) = raw.split_at(length);
    *raw = remaining;
    Ok(value)
}

fn count(raw: &mut &[u8]) -> Result<usize, &'static str> {
    let bytes = take(raw, 2)?;
    let value = usize::from(u16::from_le_bytes([bytes[0], bytes[1]]));
    if !(1..=64).contains(&value) { return Err("audit_input_count"); }
    Ok(value)
}

pub fn parse(mut raw: &[u8]) -> Result<Vec<Case<'_>>, &'static str> {
    if raw.len() > LIMIT { return Err("audit_input_too_large"); }
    let configured = match take(&mut raw, 8)? {
        b"AETHAUD3" => false,
        b"AETHAUD4" => true,
        _ => return Err("audit_input_version"),
    };
    let total = count(&mut raw)?;
    let mut cases = Vec::with_capacity(total);
    for _ in 0..total {
        let (system, component) = if configured {
            let sender = take(&mut raw, 2)?;
            if sender[0] == 0 || sender[1] == 0 { return Err("audit_sender_domain"); }
            (sender[0], sender[1])
        } else { (1, 1) };
        let size = count(&mut raw)?;
        let mut steps = Vec::with_capacity(size);
        for _ in 0..size {
            let header = take(&mut raw, 20)?;
            let op = header[0];
            let valid = header[1];
            let clock = u128::from_le_bytes(header[2..18].try_into().map_err(|_| "clock_width")?);
            let length = usize::from(u16::from_le_bytes([header[18], header[19]]));
            if op > 2 || valid > 1 || (valid == 0 && clock != 0) { return Err("audit_input_tag"); }
            if length > 320 || (op != 0 && length != 0) { return Err("audit_input_packet"); }
            steps.push(Step {
                op, now: if valid == 1 { Some(clock) } else { None },
                packet: take(&mut raw, length)?,
            });
        }
        cases.push(Case { system, component, steps });
    }
    if !raw.is_empty() { return Err("audit_input_trailing"); }
    Ok(cases)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn golden() -> Vec<u8> {
        let mut raw = b"AETHAUD3\x01\x00\x01\x00\x00\x01".to_vec();
        raw.extend(257u128.to_le_bytes());
        raw.extend([2, 0, 253, 255]);
        raw
    }

    #[test]
    fn exact_values_and_borrowed_packet() {
        let raw = golden();
        let cases = parse(&raw).unwrap();
        assert_eq!(cases.len(), 1);
        assert_eq!(cases[0].steps.len(), 1);
        assert_eq!(cases[0].steps[0].op, 0);
        assert_eq!(cases[0].steps[0].now, Some(257));
        assert_eq!(cases[0].steps[0].packet, &[253, 255]);
        assert_eq!(cases[0].steps[0].packet.as_ptr(), raw[32..].as_ptr());
    }

    #[test]
    fn configured_sender_versions_and_zero_rejection() {
        let legacy = golden();
        let parsed = parse(&legacy).unwrap();
        assert_eq!((parsed[0].system, parsed[0].component), (1, 1));
        for (system, component) in [(1, 255), (255, 1), (255, 255)] {
            let mut raw = b"AETHAUD4\x01\x00".to_vec();
            raw.extend([system, component]);
            raw.extend(&legacy[10..]);
            let parsed = parse(&raw).unwrap();
            assert_eq!((parsed[0].system, parsed[0].component), (system, component));
            assert_eq!(parsed[0].steps[0].packet.as_ptr(), raw[34..].as_ptr());
            for end in 0..raw.len() { assert!(parse(&raw[..end]).is_err()); }
            for offset in [10, 11] {
                let mut bad = raw.clone(); bad[offset] = 0;
                assert!(matches!(parse(&bad), Err("audit_sender_domain")));
            }
        }
    }

    #[test]
    fn all_truncations_trailing_and_invalid_headers() {
        let raw = golden();
        for end in 0..raw.len() { assert!(parse(&raw[..end]).is_err()); }
        let mut extra = raw.clone(); extra.push(0);
        assert!(parse(&extra).is_err());
        assert!(parse(&vec![0; LIMIT + 1]).is_err());
        for (offset, value) in [(0, 0), (8, 0), (8, 65), (10, 0), (10, 65), (12, 3),
                                (13, 2), (13, 0), (12, 1), (12, 2), (30, 255), (31, 255)] {
            let mut bad = raw.clone(); bad[offset] = value;
            assert!(parse(&bad).is_err(), "offset {offset}, value {value}");
        }
    }

    #[test]
    fn clock_extremes_and_invalid_sentinel() {
        for value in [0, u128::MAX] {
            let mut raw = golden();
            raw[14..30].copy_from_slice(&value.to_le_bytes());
            assert_eq!(parse(&raw).unwrap()[0].steps[0].now, Some(value));
        }
        let mut raw = golden(); raw[13..30].fill(0);
        assert_eq!(parse(&raw).unwrap()[0].steps[0].now, None);
    }

    #[test]
    fn short_reads_interruptions_and_byte_bound() {
        struct Tiny { raw: std::io::Cursor<Vec<u8>>, interrupted: bool }
        impl Read for Tiny {
            fn read(&mut self, buffer: &mut [u8]) -> io::Result<usize> {
                if !self.interrupted {
                    self.interrupted = true;
                    return Err(io::Error::from(io::ErrorKind::Interrupted));
                }
                let length = buffer.len().min(3);
                self.raw.read(&mut buffer[..length])
            }
        }
        let raw = golden();
        assert_eq!(read(Tiny { raw: io::Cursor::new(raw.clone()), interrupted: false }).unwrap(), raw);
        assert_eq!(read(io::Cursor::new(vec![0; LIMIT])).unwrap().len(), LIMIT);
        assert_eq!(read(io::Cursor::new(vec![0; LIMIT + 1])).unwrap_err().kind(), io::ErrorKind::InvalidData);
    }
}
