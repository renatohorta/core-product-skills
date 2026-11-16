# Discovery conversation — the ritual

Discovery is a conversation, not a form. This reference is the order of the
conversation and the gates inside it; the recorded document is described in
`cp-discover`'s packet (one `## <Section>` per artifact).

Adapted from the brainstorming discipline measured in `obra/superpowers`
(ADR-0019): the parts that survived are the ones that change what gets built.

## 1. Look before you ask

In an existing project, read before your first message: the files the user
pointed at, the code the change touches, `.context/` (discovery, requirements,
board). Never ask what the project already answers, and never reopen a decision
the user already made. The packet's "earlier artifacts" section is the floor,
not the ceiling.

## 2. The first message

Two cases:

- **The user already said what they want** (a spec, a plan, a detailed request):
  echo it back in your own words, in about 200 words — what they want, who it is
  for, why, as far as they said it — plus what you found that bears on it (how
  the relevant parts work today, what the change touches, and any constraint or
  conflict they may not have considered). End with one line inviting
  corrections, and with the one question whose answer would most change what
  gets built.
- **They have not**: one open question, in their own terms, about the biggest
  thing the request leaves unsettled — and say what the answer would change. For
  "a site for my bakery": "If it is mostly for people deciding whether to stop
  by, I would lead with hours and what is in the case today; taking orders is a
  different site. What should someone do when they land on it?"

If they did not ask for a discovery conversation and the request is clear
enough, do not force one: say so and propose to go ahead — the rest of the
chain (`cp-backlog` → `cp-build`) is the answer.

## 3. Lay out the approaches — before writing the document

Once you understand what they want, put the ways of building it in a message of
its own:

- name the two or three real alternatives (drop the weak ones, and any the
  existing code rules out), each concrete enough to picture;
- one line each on what it trades off;
- recommend one and say why;
- ask which way they want to go.

When there is genuinely one sensible way, say so in that message, explain why
the others do not fit, and go on. This is about **how** it gets built; the
**what** comes from their own words.

## 4. Play it back, in chunks

As soon as one part is clear enough to describe — what it is for and who it
serves, or how one piece behaves — describe that part back in about 200-300
words, then return to questions about the next part. Playback and questions
alternate. End each chunk with "what is wrong or missing here?".

Only what the user said goes in as theirs. Anything you filled in goes in as
your proposal, with your reason.

## 5. Size the work

Say in plain words how big it is before writing:

| Size | The recorded document |
|------|-----------------------|
| A small change | short: what you already covered together, in a line each |
| A project | the full artifact set the packet asks for |

If it grows mid-task, stop, say so and step up a size. If it is really several
independent projects, say so, agree on an order, and discover them one at a
time.

## 6. The gate

Nothing gets built until the user approves the discovery document. Building
includes code, scaffolding, dependencies and running `cp-build`. Reading,
exploring and a spike they explicitly approved are not building.

## 7. Spike, when words are not enough

A quick throwaway build is often the cheapest way to learn what they want.
Offer it when it would help. A spike gets no tests (or minimal ones), skips the
plan and the review, and stays labelled throwaway: keeping any of it is a new
request that comes back through the gate above.

## Red flags

| Thought | Reality |
|---|---|
| "I will offer a menu of what they might want" | Options steer. Ask them to describe it first. |
| "I will fill in sensible defaults" | Fine — say them out loud. A default they never heard is one they could not reject. |
| "I have answered their questions, so I will write the document" | Lay out the approaches first, in a message of its own. |
| "They said it sounds good" | Approval covers what you showed them. A document you have not written is not approved. |
| "The spike works, I will keep building on it" | Keeping it is a new request. Back through the gate. |
