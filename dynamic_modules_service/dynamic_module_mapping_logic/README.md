# Dynamic Module Mapping Logic — Developmental & Educational Matrix

This folder establishes the formal clinical and educational mapping connecting:
1. **Child Chronological Age**: Grounded in global 90% speech sound acquisition norms (**Crowe & McLeod, 2020**; **McLeod & Crowe, 2018**).
2. **DepEd Grade Level**: Anchored in the **Department of Education MATATAG Curriculum Standards** (Kindergarten, Grade 1, Grade 2, Grade 3).
3. **Phonological Process Errors**: Aligned with the 19 clinical process detectors in the **Voice Voyage Phoneme Service**.

---

## Document Index

| Document | Description |
| :--- | :--- |
| **[`age_by_age_clinical_profiles.md`](./age_by_age_clinical_profiles.md)** | **Age-by-Age Clinical Profiles (Ages 4 to 8)**: Detailed consonant inventories, expected vs. delayed errors, and clinical examples for Ages 4, 5, 6, 7, and 8. |
| **[`age_grade_process_matrix.md`](./age_grade_process_matrix.md)** | **Master Mapping Table**: Age $\rightarrow$ Grade $\rightarrow$ Process $\rightarrow$ Suppression Age $\rightarrow$ Clinical Status $\rightarrow$ Service Log Token. |
| **[`developmental_vs_atypical_rules.md`](./developmental_vs_atypical_rules.md)** | **Clinical Decision Tree**: Step-by-step logic for classifying errors into *Expected Error*, *Delayed*, and *Red Flag (Atypical)*. |
| **[`deped_curriculum_anchors.md`](./deped_curriculum_anchors.md)** | **Educational Standards**: MATATAG competencies, syllable targets, and gameplay islands mapped to each grade level. |
| **[`phoneme_service_logging_spec.md`](./phoneme_service_logging_spec.md)** | **Service Logging Specification**: Concrete log formats, JSON structures, and telemetry outputs for the phoneme service. |
| **[`mapping_schema.json`](./mapping_schema.json)** | **Machine-Readable Schema**: Complete JSON dataset for runtime validation and detector configuration. |

---

## Core Classification Taxonomy

Every detected speech sound deviation is assigned one of three standardized clinical statuses:

```
                  ┌────────────────────────────────────────────────────────┐
                  │                 Detected Speech Error                  │
                  └───────────────────────────┬────────────────────────────┘
                                              │
                    ┌─────────────────────────┴────────────────────────┐
                    ▼                                                  ▼
      ┌──────────────────────────┐                       ┌──────────────────────────┐
      │  Developmental Process   │                       │   Atypical Process       │
      │  (Historically Typical)  │                       │   (Non-Developmental)    │
      └─────────────┬────────────┘                       └─────────────┬────────────┘
                    │                                                  │
          Age < Suppression Age?                                       │
         ┌──────────┴──────────┐                                       │
         ▼                     ▼                                       ▼
┌──────────────────┐ ┌──────────────────┐            ┌──────────────────────────────┐
│  EXPECTED ERROR  │ │     DELAYED      │            │     RED FLAG (ATYPICAL)      │
│ (Age-Appropriate)│ │(Past Suppression)│            │(Immediate Clinical Referral) │
└──────────────────┘ └──────────────────┘            └──────────────────────────────┘
```

1. **`Expected Error`**: The phonological process is developmentally normal for the child's chronological age and grade level.
2. **`Delayed`**: The phonological process has persisted beyond its empirical age-normative suppression milestone, warranting targeted home practice and gameplay intervention.
3. **`Red Flag (Atypical)`**: The process is non-developmental and rarely/never occurs in typical speech development at any age, indicating a potential phonological disorder or Childhood Apraxia of Speech (CAS) requiring SLP referral.
