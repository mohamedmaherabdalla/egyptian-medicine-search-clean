# Experiment 7: Pharmacist User Study Protocol

## Status

Prepared, not executed. No result may be reported until real participants have
completed the study. Obtain the required institutional ethics approval before
recruitment, and use only deidentified prescription crops.

## Question

Does Algorithm 4 improve correct commercial-family identification and reduce
unsafe wrong selections compared with no search tool and DrugEye?

## Design

- Within-subject comparison with 15 pharmacists or senior pharmacy students.
- Seventy-five deidentified handwritten prescription word crops.
- Conditions: `no_tool`, `drugeye`, and `algorithm_4`.
- Each participant completes all three conditions but sees each crop once. This
  prevents remembering an answer from one tool condition when seeing the same
  crop again.
- Case order is randomized per participant. Condition assignment rotates by
  participant and case, so every case receives each condition across the group.
- The default 15-participant design is exactly balanced: each case is evaluated
  five times under each condition and each participant sees 25 cases per
  condition.

The available local inputs are isolated 512-by-512 RxHandBD prescription word
crops, not full prescription pages. Claims must use the term “word crops.” A
future full-page study needs page-level deidentification, segmentation, and
separate region-level ground truth.

## Participant task

For each crop, the participant chooses one action:

1. `select`: enter the commercial family they believe is written.
2. `cannot_decide`: record that the crop does not contain enough evidence.
3. `call_doctor`: defer because confirming the prescription is the safe action.

The last two are valid safe actions. The interface must never force a medicine
selection.

Algorithm 4 and DrugEye receive text, not the image. Under either tool
condition, the participant first types the letters they can read in the crop,
then uses the returned candidates. Record that exact text in `entered_query` and
link the raw tool response through `tool_output_snapshot_id`. Under `no_tool`,
the participant decides from the crop alone and both fields remain blank.

### Conditions

- `no_tool`: show only the crop and the standard response controls.
- `drugeye`: show the crop and a frozen DrugEye result captured under the study
  date, URL, participant-entered query, and browser configuration. Record
  outages and empty responses rather than silently retrying until a result
  appears.
- `algorithm_4`: show the crop and the deployed Algorithm 4 candidate list.
  Store the participant-entered query and freeze the Git commit, catalog
  checksum, deployment URL, and response JSON.

The no-tool condition must not expose candidate names. Tool conditions must use
the same visual layout, candidate count, typography, and action controls so the
comparison changes the search source, not the interface.

## Case preparation

`pharmacist_study.py prepare` selects 75 of 132 locally available crops with
unique exact Egyptian-catalog mappings. It samples round-robin across target
families before taking additional examples, then randomizes the selected set.
The participant manifest excludes expected answers. `answer_key.csv` remains
available only to the evaluator.

Before the study, two independent pharmacists must confirm every crop’s expected
family. Resolve disagreements before locking the answer key. Exclude unreadable
or disputed labels with a written reason. Do not replace a disputed label using
Algorithm 4, DrugEye, or OCR output.

## Outcomes

### Primary

- Unsafe error rate: selected wrong family divided by all trials.
- Correct decision rate: selected verified family divided by all trials.

### Secondary

- Safe deferral rate: `cannot_decide` or `call_doctor` divided by all trials.
- Decision time, from crop display until final action.
- Confidence on a 1-to-5 scale.

Report correct selection and safe deferral separately. Combining them into one
“success” score would hide whether a system helps identification or merely makes
participants defer more often.

## Procedure

1. Obtain consent and assign an anonymous participant ID.
2. Give a fixed training block that is not part of the 75 scored crops.
3. Explain all three actions and state that deferral is acceptable.
4. Run randomized trials from `assignments.csv` without revealing ground truth.
5. Record condition, selected family, action, decision time, confidence, and
   optional note for every trial.
6. Export the completed response table without names, emails, or patient data.
7. Lock the table before analysis.

## Analysis

The unit for uncertainty is the participant, not the trial. Compute each
participant’s metric under each condition, then compare conditions within that
participant. Report condition means and participant-level 95% bootstrap
intervals. The 10-to-20 participant range supports an exploratory industry
study, not a definitive clinical-effect claim. A confirmatory study requires a
prospective power calculation using the observed paired effect and variance.

Run:

```bash
python3 benchmark_04_experiments/pharmacist_study.py analyze \
  --responses benchmark_04_experiments/artifacts/03_pharmacist_study/completed_responses.csv
```

The analyzer rejects an empty response file. This prevents a prepared assignment
from being mistaken for an executed study.

## Required audit fields

- Ethics approval or exemption identifier.
- Participant role and experience band, stored separately from responses.
- Crop-set checksum and answer-key review record.
- DrugEye URL, access date, raw outputs, and outage log.
- Algorithm 4 commit, catalog checksum, deployment URL, and raw outputs.
- Randomization seed and assignment table.
- Prespecified exclusions and every excluded trial.
