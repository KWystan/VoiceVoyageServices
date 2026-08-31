# Clinical Decision Rules: Expected vs. Delayed vs. Atypical Errors

This document defines the formal decision logic implemented in the **Voice Voyage Phoneme Service** and **Dynamic Modules Service** to classify detected phonological errors.

---

## 1. Classification Definitions

### 1.1 `Expected Error` (Age-Appropriate)
- **Clinical Meaning**: The child produces a phonological error that is statistically typical for their chronological age.
- **System Action**:
  - Logged with `_EXPECTED` suffix (e.g., `GLIDE_R_EXPECTED`).
  - Scored as developmental; not penalized as a clinical disorder.
  - Generates supportive practice content without triggering clinical concern.

### 1.2 `Delayed` (Clinically Significant Developmental Delay)
- **Clinical Meaning**: The child produces a typical phonological process that has persisted past its empirical 90% suppression milestone.
- **System Action**:
  - Logged with `_DELAYED` suffix (e.g., `FRONT_VELAR_DELAYED`).
  - Generates prioritized targeted practice modules in the Dynamic Modules Service.
  - Highlighted on the Parent / SLP dashboard as an area requiring intervention.

### 1.3 `Red Flag (Atypical)` (Non-Developmental Error)
- **Clinical Meaning**: The child exhibits an error pattern that does not occur in typical speech acquisition (e.g. Backing, Initial Consonant Deletion).
- **System Action**:
  - Logged with `_ATYPICAL` suffix (e.g., `ICD_ATYPICAL`, `BACKING_ATYPICAL`).
  - Immediately flags an **SLP Referral Recommendation** in the clinical report.
  - Excludes high-risk patterns from self-guided unsupervised practice to prevent reinforcement of compensatory motor patterns.

---

## 2. Decision Tree Algorithm

```text
FUNCTION Classify_Phonological_Error(process_name, target_phoneme, child_age_years, child_grade):
    
    // -----------------------------------------------------------------------
    // STEP 1: Check for Non-Developmental (Atypical) Patterns
    // -----------------------------------------------------------------------
    IF process_name IN ["Initial Consonant Deletion", 
                        "Medial Consonant Deletion", 
                        "Backing", 
                        "Liquidization", 
                        "Frication", 
                        "Denasalization"]:
        RETURN {
            "status": "Red Flag (Atypical)",
            "log_token": process_name.upper().replace(" ", "_") + "_ATYPICAL",
            "clinical_severity": "High (Non-Developmental)",
            "recommendation": "Recommend Speech-Language Pathologist (SLP) consultation"
        }

    // -----------------------------------------------------------------------
    // STEP 2: Determine Age-Normative Suppression Threshold
    // -----------------------------------------------------------------------
    suppression_age = GET_SUPPRESSION_AGE(process_name, target_phoneme)

    // -----------------------------------------------------------------------
    // STEP 3: Compare Chronological Age against Milestone
    // -----------------------------------------------------------------------
    IF child_age_years < suppression_age:
        RETURN {
            "status": "Expected Error",
            "log_token": process_name.upper().replace(" ", "_") + "_EXPECTED",
            "clinical_severity": "Normal Developmental",
            "recommendation": "Encourage natural home practice and gameplay engagement"
        }
    ELSE:
        RETURN {
            "status": "Delayed",
            "log_token": process_name.upper().replace(" ", "_") + "_DELAYED",
            "clinical_severity": "Clinically Significant Delay",
            "recommendation": "Prioritize for structured dynamic learning module"
        }
```

---

## 3. Sound-Specific Suppression Milestones Table

| Process | Target Sound(s) | Suppression Age (Years;Months) | Reference Citation |
| :--- | :--- | :---: | :--- |
| **Stopping** | `/f/` | **3;6** | Crowe & McLeod (2020) |
| **Stopping** | `/s, z/` | **4;6** | Crowe & McLeod (2020) |
| **Stopping** | `/v/` | **5;6** | Crowe & McLeod (2020) |
| **Stopping** | `/ʃ, ʒ, θ, ð/` | **6;0–7;0** | Crowe & McLeod (2020) |
| **Velar Fronting** | `/k, ɡ/` | **3;6–4;0** | Crowe & McLeod (2020) |
| **Palatal Fronting** | `/ʃ/` | **4;6–5;0** | Crowe & McLeod (2020) |
| **Deaffrication** | `/tʃ, dʒ/` | **4;6** | Crowe & McLeod (2020) |
| **Gliding** | `/l/` | **5;0** | Crowe & McLeod (2020) |
| **Gliding** | `/r/` | **6;0** | Crowe & McLeod (2020) |
| **Vowelization** | Syllable-final `/l, r/` | **5;0–6;0** | Crowe & McLeod (2020) |
| **Weak Syllable Deletion** | Multisyllabic words | **4;0** | McLeod & Crowe (2018) |
| **Cluster Reduction (2-Element)** | `/st, sp, sk, bl, pl, fl, tr, dr/` | **4;0** | McLeod & Crowe (2018) |
| **Cluster Reduction (3-Element)** | `/str, spr, skr/` | **5;0** | McLeod & Crowe (2018) |
| **Final Consonant Deletion** | Coda consonants | **3;0–3;3** | Grunwell (1987) |
| **Prevocalic Voicing** | Onset voiceless stops/fricatives | **3;0** | McLeod & Crowe (2018) |
| **Devoicing / Final Devoicing** | Coda/Medial voiced consonants | **3;0–4;0** | Crowe & McLeod (2020) |
| **Reduplication** | Multisyllabic reduplication | **2;6–3;0** | McLeod & Crowe (2018) |
| **Consonant Harmony** | Contextual assimilation | **3;0–3;6** | McLeod & Crowe (2018) |
