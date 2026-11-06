# Scope — targeted device-state restore for the differential harness

Option 1 from the "what is a savestate" discussion: instead of a general savestate of the whole
machine, restore only the state that makes the harness's comparisons lie, and only around the
comparison. Written 2026-11-06.

## The problem being fixed

`Replay` compares a call by journalling **RAM** writes, undoing them, and re-running the call in
the interpreter. Everything that is not RAM keeps moving between the two runs, so a call whose
subtree touched such state cannot be compared honestly. The harness currently does the only
safe thing: it skips those calls.

Measured cost of skipping (400-frame run): **151,659 calls skipped**, of which 150,246 were
"device writes". Those are exactly the calls this scope would make comparable.

## What the fault needs — the minimal set

The failing interval is the GD-ROM syscall stub (`0x8C175B54..0x8C175B84`) and the task switch
that follows it, so the state that matters is the state those paths touch. Inventory, with the
member that holds it:

| Subsystem | State | Where | Size | Restore |
|---|---|---|---|---|
| AICA registers | `regs_` | `aica/aica.h` (`std::array<std::uint8_t,0x8000>`) | 32 KB | `memcpy` |
| AICA timers | `timer_step_`, `timer_left_`, `samples`, `event_` | `aica/aica.h` | ~40 B | assign |
| ARM7 CPU | register file (r0–r15, CPSR, SPSR + banked), `n/z/c/v`, `irq_enable_`, `fiq_enable_`, `enabled_`, `mode_`, `ticks_`, `aica_interr_`, `e68k_out_` | `aica/arm7.h` | ~250 B | `memcpy` + assign |
| Mixer DSP | `DspState dsp_` | `aica/mixer.h` | small | assign |
| GD-ROM driver | `Gd gd_` (status, `result[]`, `params[]`, sector, transfer) + `gd_event_` | `hle/bios.h` | ~200 B | assign |
| Scheduler | `events_` (id, deadline, armed), `now_` | `sched/scheduler.h` | ~N×24 B | copy vector |
| Holly interrupts | pending/normal/external masks | `holly/intc.*`, `holly/sysblock.*` | tens of B | assign |

AICA sound RAM (2 MB) and main RAM (16 MB) are **already** covered: sound RAM is memory the
journal sees, and main RAM is the journal itself. VRAM is not touched by this interval.

## Deliberately excluded, and what it costs

| Excluded | Consequence |
|---|---|
| PVR registers, TA FIFO, VRAM | Rendering state can still drift across a comparison. Fine for calls that do not touch the PVR; a future iteration can add `pvr::` registers the same way. |
| Maple device/VMU | A comparison that polls the controller still lies. The VMU image is file-backed and must not be replayed twice at all. |
| RTC wall-clock | Non-deterministic by nature; the harness already fixes it with `--rtc-seed`. |
| Host audio queue | Not emulated state; the comparison runs headless. |

This is the point of the "targeted" scope: it fixes the calls that matter for this fault and
makes the omission explicit instead of pretending the harness is complete.

## API sketch

```cpp
// runtime/include/dream/runtime/debug/device_snapshot.h
namespace dream::debug {

// The subset of device state a function comparison must rewind. Not a savestate: no memory
// images, no rendering state — just what the GD/AICA/scheduler paths mutate.
struct DeviceSnapshot {
    std::array<std::uint8_t, 0x8000> aica_regs;
    std::uint64_t aica_samples, now;
    std::array<int, 3> timer_step, timer_left;
    int aica_event, gd_event;
    Arm7State arm;
    MixerDspState dsp;
    hle::Bios::Gd gd;
    sched::Scheduler::Events events;
    std::uint32_t istnrm, istext;
};

void capture(DeviceSnapshot& out, Aica&, Bios&, Sched&, Intc&);
void restore(const DeviceSnapshot& in, Aica&, Bios&, Sched&, Intc&);

}  // namespace dream::debug
```

Two accessors are needed on classes that keep their members private: `Aica::save_state()/load_state()`
and `Bios::save_gd()/load_gd()`. Everything else is public or already exposed.

## Integration into the harness

```cpp
void Replay::enter(function) {
    ...
    debug::capture(snapshot_, aica, bios, sched, intc);   // once, at the comparison point
}
void Replay::exit(function) {
    ...
    memory_.undo_journal();          // RAM, as today
    debug::restore(snapshot_, ...);  // <-- new: device state
    run(ctx_, memory_, entry_.pr, opt, nullptr);
}
```

The snapshot is taken once per compared call, not per instruction, so the cost is a ~35 KB
memcpy in and out — negligible next to a function that runs thousands of instructions.

## Tests

1. **Round-trip identity** (unit): capture → mutate every field → restore → assert byte equality
   for each subsystem. One test per subsystem, so a missed field fails loudly.
2. **Harness regression**: the GD false positive of `fn_0c22caa4` must now compare *and* agree,
   instead of being skipped. That case is already understood and reproducible.
3. **Skip-count expectation**: `skipped_device` should fall from ~150k to near zero over a
   400-frame run, with disagreements still zero. A disagreement appearing here would be a real
   finding, not a skip.
4. **Determinism**: two runs with the same seed produce identical counters.

## Effort

| Task | Estimate |
|---|---|
| `DeviceSnapshot` + `capture/restore` | 120–180 lines |
| Accessors on `Aica` and `Bios` | 40 lines |
| Harness wiring | 20 lines |
| Unit tests (4) | 120 lines |
| Rerun + triage | half a day |
| **Total** | **1–1.5 days** |

## Risks

* **Completeness.** A field left out makes a comparison lie silently — the exact failure mode that
  cost several sessions. The per-subsystem round-trip tests are the mitigation, and they should be
  written before the wiring, not after.
* **Order of restore vs journal.** The journal must be undone first (RAM), then device state, or a
  device read during restore sees half-rolled-back memory.
* **Device side effects inside the compared call are still repeated.** This scope makes the
  comparison *see* the right state; it does not stop the GD-ROM from being read twice. For a
  driver that is idempotent per LBA that is fine; a stateful command sequence would still need a
  skip.

## Acceptance

* `skipped_device` near zero on a 400-frame run, `0 disagreements`.
* The four unit tests pass.
* The engine's own suite still passes (`100 %`, with `TMP` redirected).
* The within-run differential still shows the GD call's two executions agreeing when compared
  with device state restored.
