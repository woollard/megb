# MEGB Ticket Index

**Active tickets in this directory (`tickets/megb-0N.md`) govern.** Files under
`tickets/archive/` are retained only as historical context for audit purposes —
their requirements must never be combined with, or treated as an alternative
source of truth alongside, the active specification for the same epic number.

Where an active ticket's own text states a specification version and a
"Supersedes" note, that note identifies which archived file(s) it replaces.
Superseded language is preserved only in `tickets/archive/`, never repeated as
an alternative operating rule in the active ticket.

## Canonical Specification Table

| Epic | Active path | Specification version | Status (per ticket) | SHA-256 | Archive / superseded location |
| --- | --- | --- | --- | --- | --- |
| MEGB-01 | [`megb-01.md`](megb-01.md) | — (no version header in ticket) | No epic-status header in ticket | `9598ece5f87f6c0c22ecaee2bef8f82cfbad121f4b38576d58e83737a6e07136` | none |
| MEGB-02 | [`megb-02.md`](megb-02.md) | — (no version header in ticket) | No epic-status header in ticket | `d551be8591b63be09c65df9a5789e8d98a0b7181c0828bcb0c653e1be88f3c3f` | none |
| MEGB-03 | [`megb-03.md`](megb-03.md) | — (no version header in ticket) | In progress — see ticket's own "Epic Status" section for the current per-subtask breakdown | `2cfe61348624b171c1ab0244163344182d4d16ffeead2eef85090aad2cf414b0` | none |
| MEGB-04 | [`megb-04.md`](megb-04.md) | `megb-04-ticket-v2` | Not started | `a3dd6ddd1da9226229effd58b58d4dfae2075ba8d4678baa4c49016ff335dc9a` | [`archive/MEGB-04.md`](archive/MEGB-04.md) (historical monolithic ticket) |
| MEGB-05 | [`megb-05.md`](megb-05.md) | `megb-05-ticket-v2` | Not started | `07aada70996fd9487f1d7360fd57cc1169498f4633f9f3796a8febb3fb416a54` | [`archive/MEGB-05.md`](archive/MEGB-05.md) (historical monolithic ticket) |
| MEGB-06 | [`megb-06.md`](megb-06.md) | `megb-06-ticket-v2` | Not started | `fcc80f395ad8ba9395fb828afc8df0cd80ef015cf971e6dd2d6e4ea246914bc0` | [`archive/MEGB-06.md`](archive/MEGB-06.md) (historical monolithic ticket) |
| MEGB-07 | [`megb-07.md`](megb-07.md) | — (ticket states "Authoritative refactored ticket"; no version string) | Not started | `345932189e0a58fab18589a0151df7245363cc731cb6b6a5b90eb957a0fc0e9e` | [`archive/MEGB-07.md`](archive/MEGB-07.md) (historical monolithic ticket) |
| MEGB-08 | [`megb-08.md`](megb-08.md) | — (ticket states "Authoritative refactored ticket"; no version string) | Not started | `5857010ce2cbe19bde1bffa481450135492a9736d3058b248cfa7d94563ce3eb` | [`archive/MEGB-08.md`](archive/MEGB-08.md) (historical monolithic ticket) |
| MEGB-09 | [`megb-09.md`](megb-09.md) | — (ticket states "Prior version: None; this is a new epic") | Not started | `842c076a67db8272abf2245d09367d47e730d9254403ac232f9fb8da56cc32ea` | none (new epic; no predecessor) |

## Verifying checksums

From the repository root:

```bash
shasum -a 256 tickets/megb-01.md tickets/megb-02.md tickets/megb-03.md \
  tickets/megb-04.md tickets/megb-05.md tickets/megb-06.md \
  tickets/megb-07.md tickets/megb-08.md tickets/megb-09.md
```

Each line's digest must match the corresponding row above exactly. A mismatch
means the active ticket has drifted from the installed specification and must
be investigated before acting on it.

## Archive contents

`tickets/archive/` holds the historical, superseded uppercase-named tickets
that predate the `megb-0N-ticket-v2` (or equivalent "authoritative refactored")
specifications above:

- `archive/MEGB-04.md` — superseded by `megb-04.md` (`megb-04-ticket-v2`)
- `archive/MEGB-05.md` — superseded by `megb-05.md` (`megb-05-ticket-v2`)
- `archive/MEGB-06.md` — superseded by `megb-06.md` (`megb-06-ticket-v2`)
- `archive/MEGB-07.md` — superseded by `megb-07.md`
- `archive/MEGB-08.md` — superseded by `megb-08.md`

These files are retained for audit history only. Do not resume, cite as a
requirement source, or merge text from an archived ticket into work on the
corresponding active epic.
