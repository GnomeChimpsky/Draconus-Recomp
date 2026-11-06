# Draft — permission request to the SARecomp author

Status: **draft, not sent**. Send from the project owner's account so the reply comes
to the person who will act on it.

---

**Subject:** Permission enquiry — reusing parts of SARecomp in another Dreamcast recomp

Hi,

I'm building a static recompilation of *Draconus: Cult of the Wyrm* (Dreamcast, 2000)
for Windows x64 — a preservation project, non-commercial, with the game supplied by
the player's own disc dump. Source will be public.

SARecomp is clearly the furthest-along Dreamcast recompilation there is, and I have
been studying it as a reference — architecture, frame pacing, input layering, the
launcher/disc-import flow. I have not copied anything: the repository has no licence
file, so I have treated it as read-only and logged my reading separately.

I would like to ask whether you would consider granting permission to reuse a limited
set of **port-layer** components under a GPL-compatible licence, specifically:

* the input binding / controller-prompt layer,
* the frame-pacing / execution-clock design,
* the installer / disc-import flow.

Not the translator, not the runtime, and nothing derived from the game — those would
stay entirely my own work (I am building on `dream-recomp`, which is GPL-2.0).

If the answer is no, that is completely fine and I will keep using it as a
read-only reference, with attribution in my documentation. If it is yes, I would
rather do this in writing so the boundary is unambiguous for both of us, and I am
happy to credit you prominently and offer any improvements back.

Two questions either way:

1. Would you be comfortable with a short written note stating that no permission is
   granted, so I can record the position accurately?
2. If permission is possible, which licence and scope would you prefer?

Thank you for the work you have put into SARecomp — it is a genuinely useful reference
for everyone working in this space.

Best regards,
\<name\>
\<project URL\>

---

## Notes for the sender

* Do not attach game files, generated code, or the disc.
* Do not ask for their code before they have answered.
* Record the reply (or the absence of one) in `docs/refs/sarecomp-notes.md` with a date.
* Until a written grant exists, the boundary rules in `docs/04-REFERENCE-REPOS.md`
  apply without exception.
