# Detector 700-Entry Audit Report

Total entries: 700

## Bugs (0)

## Logical Errors - Hierarchy (0)

## Edge Cases - Position (0)

## Curriculum Gaps (60)
(216, 'gush', 'Fronting', 'Palatal Fronting', 'detection/curriculum_map.py:_AGE_PROCESS_MAP')
(224, 'marsh', 'Fronting', 'Palatal Fronting', 'detection/curriculum_map.py:_AGE_PROCESS_MAP')
(232, 'shake', 'Fronting', 'Palatal Fronting', 'detection/curriculum_map.py:_AGE_PROCESS_MAP')
(233, 'sharp', 'Fronting', 'Palatal Fronting', 'detection/curriculum_map.py:_AGE_PROCESS_MAP')
(234, 'shed', 'Fronting', 'Palatal Fronting', 'detection/curriculum_map.py:_AGE_PROCESS_MAP')
(235, 'shell', 'Fronting', 'Palatal Fronting', 'detection/curriculum_map.py:_AGE_PROCESS_MAP')
(236, 'shine', 'Fronting', 'Palatal Fronting', 'detection/curriculum_map.py:_AGE_PROCESS_MAP')
(237, 'shock', 'Fronting', 'Palatal Fronting', 'detection/curriculum_map.py:_AGE_PROCESS_MAP')
(238, 'shop', 'Fronting', 'Palatal Fronting', 'detection/curriculum_map.py:_AGE_PROCESS_MAP')
(239, 'shun', 'Fronting', 'Palatal Fronting', 'detection/curriculum_map.py:_AGE_PROCESS_MAP')
(350, 'arrow', 'Gliding', 'Gliding', 'detection/curriculum_map.py:_AGE_PROCESS_MAP')
(351, 'barrel', 'Gliding', 'Gliding', 'detection/curriculum_map.py:_AGE_PROCESS_MAP')
(352, 'bell', 'Gliding', 'Gliding', 'detection/curriculum_map.py:_AGE_PROCESS_MAP')
(353, 'berry', 'Gliding', 'Gliding', 'detection/curriculum_map.py:_AGE_PROCESS_MAP')
(354, 'celery', 'Gliding', 'Gliding', 'detection/curriculum_map.py:_AGE_PROCESS_MAP')
(355, 'corner', 'Gliding', 'Gliding', 'detection/curriculum_map.py:_AGE_PROCESS_MAP')
(356, 'farmer', 'Gliding', 'Gliding', 'detection/curriculum_map.py:_AGE_PROCESS_MAP')
(357, 'fell', 'Gliding', 'Gliding', 'detection/curriculum_map.py:_AGE_PROCESS_MAP')
(358, 'fill', 'Gliding', 'Gliding', 'detection/curriculum_map.py:_AGE_PROCESS_MAP')
(359, 'hill', 'Gliding', 'Gliding', 'detection/curriculum_map.py:_AGE_PROCESS_MAP')

## Score Anomalies (0)

## Missing Detectors
('Metathesis', 'No entries test phoneme reordering (e.g., ask -> aks); no metathesis detector exists', 'detection/detectors/* (no metathesis module)')
('Assimilation/Consonant Harmony', 'No entries test progressive assimilation beyond voicing (e.g., dog -> gog is Backing, but harmony not separate); harmony detector gap', 'detection/detectors/substitution.py')
('Epenthesis', "No entries test inserted vowel/consonant (child longer than target); inserted phonemes produce breakdown with expected='-' which detectors ignore", 'detection/detectors/deletion.py + gates.py')
('Frication/Denasalization/Liquidization gaps in dataset', 'Dataset covers 14 of 17 detector processes; Frication, Denasalization, Liquidization never appear in dataset (50 each missing would be 150 entries). Curriculum includes them but dataset lacks coverage', 'detection/detectors/substitution.py')
