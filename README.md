---
title: VirtualMDT-Rx
emoji: 🩺
colorFrom: green
colorTo: blue
sdk: gradio
sdk_version: 6.32.0
app_file: app.py
pinned: false
license: mit
---

# VirtualMDT-Rx

**A virtual multidisciplinary team (MDT) for safer prescribing by GPs and consultants.**

> **Research demonstrator on invented data. Not a medical device.** The medicine rules are a small, paraphrased,
> illustrative set. They are not the BNF, NICE guidance or a licensed drug database, and they are not kept up to date.
> Do not enter real patient details and do not use this tool to make real prescribing decisions.

In hospital, a prescription is often checked by a team: pharmacist, therapists and specialists. A GP usually
prescribes alone, in a ten-minute appointment. VirtualMDT-Rx gathers a *virtual* team for every prescribing request,
runs all the experts at the same moment, and hands the prescriber a checked draft with the reasons. The clinician
always makes the decision.

It implements and extends the design in:

> Rajagopal N., Jagini A., Ramachandran M. (2026). *A Multiagent AI Framework for Parallelised Prescription Decision
> Support in Primary Care.* ABH 2026, Porto.

## Try it

**Google Colab:** open `notebooks/VirtualMDT_Rx_Colab.ipynb` in Colab and choose *Runtime > Run all*.

**Your own computer:**

```bash
git clone https://github.com/Muthuuk/VirtualMDT-Rx.git
cd VirtualMDT-Rx
pip install -r requirements.txt
python app.py
```

**Hugging Face Spaces:** create a Gradio Space and push this repository to it. The block at the top of this file
is the Space configuration.

## What you see

The home page shows six 3D colour buttons. Each opens its own page, with a Home button to come back.

**Make it fit your screen and your eyes.** At the top of every page, *Display size* (Compact, Comfortable, Large) resizes
everything in one click, so the browser zoom is not needed, and *Colours* switches between Light, Dark and High
contrast. Both choices are remembered on your device. Verdicts carry a shape (✓ ▲ ✕) as well as a colour.

| Button | What it opens |
|---|---|
| Convene the virtual MDT | Enter the prescribing request in three short steps (patient, medicine, tests and history), or pick an example. The meeting room then opens, sized to fit the screen: the 3D room on the left and one panel at a time on the right (Talk, Team board, Try a change, Details, Patient summary, Decide). The expert you speak to is lit up. *Quick view* hides the room and goes straight to the key points and the decision. The 3D room shows which experts were convened, their verdicts and whether each one's human counterpart can be reached now. You can ask any expert a question, go round the table, put a changed prescription to the team and see who changes position, then record your decision. A written conclusion is produced and can be downloaded. |
| Review a patient list | Run the team over a whole CSV list, or over 200 invented patients, and see what share is escalated and which rules fire most. |
| What is being prescribed | Live monthly NHS prescribing counts for urine-infection antibiotics, diabetes medicines and cancer-care medicines, from OpenPrescribing.net. |
| Engineering and assurance | The nine engineering principles, the requirements traced to tests, and ten acceptance targets you can run on the spot. |
| Decision log | Every decision recorded in the session, with a check that the log has not been altered. |
| About and limits | What is new compared with the paper, and what the tool cannot do. |

## How a request is handled

```
request ─► 1 Triage notes ─► 2 Convene team ─► 3 Experts work in parallel, each on its own slice
                                                        │
        7 Clinician decides ◄─ 6 Safety double-check ◄─ 5 Simpler-regimen ideas ◄─ 4 Combine findings
```

* **Core team (always):** Pharmacist, Side-effect check, Physio/OT, Allergy Safety, Guidance, Literature.
* **Medicine-by-medicine check:** the new medicine's main side effects are listed, and it is checked against every
  existing medicine for named interactions and for side effects that add up (for example two medicines that both cause
  drowsiness). An existing medicine that cannot be checked is shown as *not checked*, never skipped.
* **Called in when needed:** Microbiologist, Urologist, Diabetologist, Oncologist, Kidney physician, Geriatrician.
* **Dose check:** the single dose and the total per day are compared with the usual and maximum adult dose (with a
  lower limit from age 65 where one applies). An overdose stops the request; a dose that cannot be read or has no
  limit on file is reported as *not checked*.
* **Is it really an infection?** For an antibiotic, the latest lab result is taken into account. If the test found no
  infection, no antibiotic is drafted and no drug swap is offered. Repeated clear tests prompt assessment for
  inflammation (for example bladder pain syndrome) before more antibiotics.
* **Antibiotic exposure:** total days of antibiotics over 12 months are counted. Heavy exposure and long-term
  nitrofurantoin raise warnings with the monitoring needed.
* **Outcomes:** *Ready* (green), *Ready with cautions* (amber), *Flag and escalate* (red: no draft, a safer option
  if one passes every rule), *Hard stop* (every usual option fails a rule; the clinician must resolve it).
* **Human in the loop:** nothing is issued without a named clinician's decision. An escalated case cannot simply be
  approved: the clinician takes the safer option, declines, or overrides with a written reason. Every decision goes
  into a tamper-evident log that holds no identifiers.

## What is new compared with the paper

1. The team changes with the case, instead of five fixed agents, and a side-effect expert checks the new medicine against every existing medicine.
2. A 3D consulting room with an availability rota for each expert's human counterpart (`vmdt/rota.py`; demo hours, edit to match your team).
3. A stricter sign-off step with override reasons and a hash-chained decision log.
4. A safety double-check that re-runs the hard rules without trusting the experts.
5. Whole-list review and live NHS open data.
6. A software engineering method: requirements traced to tests, acceptance targets and a release gate.

## Our software engineering approach

| Principle | Where to look |
|---|---|
| 1 Goal-driven, testable requirements | `vmdt/requirements_trace.py`, `tests/test_traceability.py` |
| 2 Safety rules outside the model | `vmdt/knowledge.py` (rules as data), `hard_checks()` in `vmdt/orchestrator.py` |
| 3 One agent, one job | `vmdt/agents.py`, with a field scope per expert |
| 4 Least-privilege tools | `vmdt/opendata.py`: read-only, medicine and condition names only |
| 5 Explicit state, reproducible | fixed route in `run_case()`; case fingerprint |
| 6 Observability and audit | per-expert timings on screen; `vmdt/audit.py` |
| 7 Evaluate before trusting | `python -m vmdt.evaluate`; `.github/workflows/ci.yml` |
| 8 Human in the loop | `sign_off()` in `vmdt/orchestrator.py` |
| 9 Ethics and privacy by design | no identifiers; salted hashes; limits stated on every screen |

```bash
pip install pytest
pytest -q                 # 86 tests
python -m vmdt.evaluate   # 10 acceptance targets; exits with an error if any fails
```

## Reviewing your own list (tab 2)

CSV columns. Only the first four are required. Lists use `;` between items.

`patient_ref, age, sex, proposed_drug, dose, frequency, duration_days, indication, egfr, pregnant, trimester,
conditions, allergies, current_meds, uti_courses_6m, culture_resistant_to, cognitive_impairment, dexterity_problem,
falls_history, frail, notes, urine_culture, clear_cultures_12m, antibiotic_days_12m`

* `indication`: `uti`, `type2_diabetes`, `cancer_care` or `other`
* `allergies`: `substance:reaction`, for example `penicillin:anaphylaxis`
* `urine_culture`: `not recorded`, `not sent`, `awaited`, `infection confirmed` or `no infection found`
* `frequency`: `once daily`, `twice daily`, `three times daily`, `four times daily`, `once weekly`, `single dose`

An invented example is in `data/sample_patients_synthetic.csv`. Use only anonymised or invented data.

## Honest limits

* Side effects and interactions come from a short illustrative list per medicine, not the full product information.
  "No clash found" means none in this list.
* Dose limits are an illustrative adult table for about 40 medicines. They ignore indication, formulation, weight and
  most kidney adjustments, and a pharmacist must confirm them before any real use.
* The NICE checks use a short paraphrased summary held in the code. The tool is not connected to NICE and will not
  follow guideline updates by itself.
* The rule set covers about 60 medicines and three areas (urine infection, type 2 diabetes, cancer care). A medicine
  it does not know is flagged for manual review, never passed silently.
* The evaluation cases and the rules were written by the same team. A perfect score shows the controls work as
  designed. It does not show clinical accuracy.
* In the meeting the experts answer a fixed set of questions from their recorded findings. They cannot answer
  free-text questions.
* The experts are rule-based programs. No language model decides anything. Each expert slot has a fixed
  input/output contract, so a properly evaluated model can replace one later without changing the rest.
* The Literature expert lists recent PubMed titles only. It does not grade or summarise evidence.
* The 3D figures are drawings of software experts, not people. The rota hours are a demonstration.
* The live NHS data tab needs internet access and depends on the OpenPrescribing service being available.

## Route to clinical use

Before any use with real patients this would need: licensed and maintained medicine content (for example dm+d and
a commercial interaction database) signed off by a pharmacist; a clinical safety case (DCB0129 and DCB0160); a data
protection impact assessment; integration with the GP record system; a shadow-mode study against clinicians'
decisions; and regulatory assessment as software as a medical device.

## Credits and licence

Concept and paper: Naveen Rajagopal, Abhijay Jagini and Muthu Ramachandran. Software: Prof Muthu Ramachandran,
Forti5 Technologies Ltd, Leeds, and CAIDS, University of South Africa. MIT licence.
Open data: OpenPrescribing.net (Bennett Institute for Applied Data Science, University of Oxford); PubMed (US
National Library of Medicine).
