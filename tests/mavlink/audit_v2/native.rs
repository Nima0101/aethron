// Original audit-only strict subset. SPDX-License-Identifier: GPL-3.0-only.
// No network, transmit API, SDK qualification, or production integration.
#![forbid(unsafe_code)]

#[derive(Clone, Copy)]
struct Sample {
    values: [f64; 6],
    boot: u32,
    receive: u128,
}

struct Step<'a> {
    op: u8,
    now: Option<u128>,
    packet: &'a [u8],
}

#[cfg(not(runtime_input))]
include!("native-fixture.rs");
#[cfg(runtime_input)]
mod runtime_input_v3;

struct Receiver {
    system: u8,
    component: u8,
    last: Option<u128>,
    sequence: Option<u8>,
    boot: [Option<u32>; 2],
    samples: [Option<Sample>; 2],
    reason: &'static str,
    latched: bool,
}

impl Receiver {
    fn new(system: u8, component: u8) -> Self {
        Self {
            system, component, last: None, sequence: None, boot: [None; 2], samples: [None; 2],
            reason: "no_observation", latched: false,
        }
    }

    fn withdraw(&mut self, reason: &'static str, latch: bool) {
        self.samples = [None; 2];
        self.reason = reason;
        self.latched |= latch;
    }

    fn clock(&mut self, now: Option<u128>) -> Option<u128> {
        if self.latched { return None; }
        match now {
            Some(value) if self.last.is_none_or(|last| value >= last) => {
                self.last = Some(value);
                Some(value)
            }
            _ => { self.withdraw("local_clock_invalid", true); None }
        }
    }

    fn ingest(&mut self, p: &[u8], now: Option<u128>) {
        let Some(now) = self.clock(now) else { return; };
        if !(12..=280).contains(&p.len()) {
            self.withdraw("invalid_packet", false); return;
        }
        if p[0] != 253 || p[2] != 0 || p[3] != 0 {
            self.withdraw("unsupported_packet", false); return;
        }
        if p.len() != usize::from(p[1]) + 12 {
            self.withdraw("invalid_packet", false); return;
        }
        let id = u32::from_le_bytes([p[7], p[8], p[9], 0]);
        let (slot, extra) = match id {
            30 => (0, 39u8), 32 => (1, 185u8),
            _ => { self.withdraw("unsupported_message", false); return; }
        };
        if !(1..=28).contains(&p[1]) {
            self.withdraw("invalid_packet", false); return;
        }
        if p[5] != self.system || p[6] != self.component {
            self.withdraw("sender_mismatch", false); return;
        }
        let mut crc = 65535u16;
        for byte in p[1..p.len()-2].iter().copied().chain(std::iter::once(extra)) {
            let mut tmp = byte ^ (crc as u8);
            tmp ^= tmp << 4;
            let tmp = u16::from(tmp);
            crc = (crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4);
        }
        if crc != u16::from_le_bytes([p[p.len()-2], p[p.len()-1]]) {
            self.withdraw("invalid_packet", false); return;
        }
        let mut payload = [0u8; 28];
        payload[..usize::from(p[1])].copy_from_slice(&p[10..p.len()-2]);
        let mut values = [0f64; 6];
        for (index, value) in values.iter_mut().enumerate() {
            let offset = 4 + index * 4;
            *value = f64::from(f32::from_le_bytes([
                payload[offset], payload[offset+1], payload[offset+2], payload[offset+3],
            ]));
        }
        if !values.iter().all(|v| v.is_finite()) {
            self.withdraw("invalid_values", false); return;
        }
        if self.sequence.is_some_and(|seq| !(1..=127).contains(&p[4].wrapping_sub(seq))) {
            self.withdraw("packet_order", false); return;
        }
        let boot = u32::from_le_bytes([payload[0], payload[1], payload[2], payload[3]]);
        if self.boot[slot].is_some_and(|previous| boot <= previous) {
            self.withdraw("source_clock_reset", true); return;
        }
        self.sequence = Some(p[4]);
        self.boot[slot] = Some(boot);
        self.samples[slot] = Some(Sample { values, boot, receive: now });
        self.reason = "unmapped_source_clock";
    }

    fn close(&mut self) {
        self.withdraw("closed", true);
        self.boot = [None; 2];
        self.sequence = None;
    }

    fn snapshot(&mut self, now: Option<u128>) -> String {
        if let Some(now) = self.clock(now) {
            let mut stale = false;
            for sample in &mut self.samples {
                if sample.is_some_and(|s| now - s.receive > 100_000_000) {
                    *sample = None; stale = true;
                }
            }
            if stale && self.samples.iter().all(Option::is_none) {
                self.reason = "receive_expired";
            }
        }
        let mut samples = Vec::with_capacity(2);
        for (slot, sample) in self.samples.iter().enumerate() {
            let Some(s) = sample else { continue; };
            let (name, frame, fields, units) = if slot == 0 {
                ("ATTITUDE", "body_euler",
                 r#"["roll","pitch","yaw","rollspeed","pitchspeed","yawspeed"]"#,
                 r#"["rad","rad","rad","rad/s","rad/s","rad/s"]"#)
            } else {
                ("LOCAL_POSITION_NED", "local_ned_unregistered",
                 r#"["x","y","z","vx","vy","vz"]"#,
                 r#"["m","m","m","m/s","m/s","m/s"]"#)
            };
            // All strings are fixed literals; floats were checked finite above.
            samples.push(format!(concat!(
                "{{\"system_id\":{},\"component_id\":{},\"message\":\"{}\",",
                "\"frame\":\"{}\",\"fields\":{},\"units\":{},\"values\":{:?},",
                "\"source_boot_ms\":{},\"receive_ns\":\"{}\",\"capture_ns\":null,",
                "\"evidence\":\"external_unverified\",\"authenticated\":false,",
                "\"link_id\":null,\"signature_timestamp\":null}}"
            ), self.system, self.component, name, frame, fields, units, s.values, s.boot, s.receive));
        }
        let state = if samples.is_empty() { "UNKNOWN" } else { "OBSERVED_UNVERIFIED" };
        format!("{{\"state\":\"{}\",\"reason\":\"{}\",\"samples\":[{}],\"perception_eligible\":false}}",
            state, self.reason, samples.join(","))
    }
}

fn main() {
    #[cfg(runtime_input)]
    let raw = runtime_input_v3::read(std::io::stdin().lock()).expect("bounded audit input");
    #[cfg(runtime_input)]
    let parsed = runtime_input_v3::parse(&raw).expect("valid audit input");
    #[cfg(runtime_input)]
    let cases: Vec<&[Step<'_>]> = parsed.iter().map(|case| case.steps.as_slice()).collect();
    #[cfg(not(runtime_input))]
    let cases = CASES;
    let mut results = Vec::with_capacity(cases.len());
    for (index, steps) in cases.iter().enumerate() {
        #[cfg(runtime_input)]
        let (system, component) = (parsed[index].system, parsed[index].component);
        #[cfg(not(runtime_input))]
        let (system, component) = SENDERS[index];
        let mut receiver = Receiver::new(system, component);
        let mut outputs = Vec::with_capacity(steps.len());
        for step in *steps {
            match step.op {
                0 => receiver.ingest(std::hint::black_box(step.packet), std::hint::black_box(step.now)),
                1 => (),
                2 => receiver.close(),
                _ => panic!("invalid audit operation"),
            }
            outputs.push(receiver.snapshot(step.now));
        }
        results.push(format!("[{}]", outputs.join(",")));
    }
    // Linux-only measurement wrapper. This is outside the receiver implementation.
    let status = std::fs::read_to_string("/proc/self/status").expect("Linux RSS receipt");
    let rss: u64 = status.lines().find_map(|line| {
        line.strip_prefix("VmHWM:").and_then(|v| v.split_whitespace().next())
    }).expect("VmHWM present").parse().expect("RSS integer");
    println!("{{\"results\":[{}],\"peak_rss_kib\":{}}}", results.join(","), rss);
}
