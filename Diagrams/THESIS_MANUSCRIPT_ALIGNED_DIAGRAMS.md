# Voice Voyage Chapter 3 Diagrams - Manuscript-Aligned Version

This Markdown file updates the Voice Voyage diagrams based on the Chapter 3 formatting pattern observed in the provided manuscript. The manuscript uses direct section headings, simple figure captions, and explanatory paragraphs beginning with phrases such as "Figure 2 shows..." or "Figure 3 illustrates..."

The attached manuscript was used only as a formatting reference. Its project-specific content about another system was not treated as an instruction for Voice Voyage.

## Recommended Chapter 3 Figure List

1. Figure 2. System Architecture
2. Figure 3. Software Architecture
3. Figure 4. Class Diagram
4. Figure 5. Use Case Diagram
5. Figure 6. Parent Sign-up and Child Screening Sequence Diagram
6. Figure 7. Speech Assessment Sequence Diagram
7. Figure 8. Adaptive Practice Plan Sequence Diagram
8. Figure 9. Gameplay Assessment Sequence Diagram
9. Figure 10. Speech Screening Flowchart Diagram
10. Figure 11. Practice Gameplay Flowchart Diagram
11. Figure 12. Error Handling Flowchart Diagram
12. Figure 13. Entity Relationship Diagram
13. Figure 14. Data Flow Diagram
14. Figure 15. Access Control Diagram
15. Figure 16. Deployment Diagram
16. Figure 17. Testing and Evaluation Flow Diagram
17. Figure 18. SDLC Agile Model

## System Architecture

Figure 2 shows the system architecture of Voice Voyage. The parent and child interact with the mobile application, while account access and stored records are handled through Firebase. The application sends recorded speech to the speech assessment service and sends screening findings to the adaptive practice plan service. The backend services use speech processing support, learning guides, and word lists to provide pronunciation feedback and personalized practice content.

```mermaid
flowchart LR
    User["Parent and Child"]

    subgraph Device["Mobile Device"]
        App["Voice Voyage App"]
        LocalData[("Temporary Recordings\nLatest Practice Plan")]
    end

    subgraph Cloud["Firebase Cloud"]
        Auth["Account Login"]
        Records[("Parent, Child, Speech,\nand Progress Records")]
        Rules["Owner-Based\nData Access"]
    end

    subgraph Backend["Voice Voyage Services"]
        Speech["Speech Assessment Service"]
        Plan["Adaptive Practice Plan Service"]
        Resources["Word Lists and\nLearning Guides"]
    end

    subgraph Support["AI and Speech Support"]
        SpeechModels["Speech Recognition and\nAudio Processing Models"]
        AI["Generative AI Helper\nwhen available"]
    end

    User --> App
    App --> LocalData
    App --> Auth
    App --> Records
    Records -. protected by .-> Rules
    App -->|"recorded speech"| Speech
    Speech --> SpeechModels
    Speech --> Resources
    App -->|"screening findings"| Plan
    Plan --> Resources
    Plan --> AI
```

Figure 2. System Architecture

## Software Architecture

Figure 3 illustrates the software architecture of Voice Voyage. The application is divided into interface, control, service, and data layers. The interface layer contains the screens used by parents and children. The control layer manages user actions and screen flow. The service layer handles login, saved records, audio recording, speech assessment, practice plan requests, and local storage. The data layer contains the models used for parent accounts, child profiles, speech profiles, learning modules, reports, and game results.

```mermaid
flowchart TB
    subgraph App["Voice Voyage Mobile Application"]
        subgraph View["Interface Layer"]
            LoginUI["Login and Sign-up Screens"]
            ProfileUI["Profile and Home Screens"]
            ScreeningUI["Speech Screening Screens"]
            GameUI["Practice Game Screens"]
            ReportUI["Learning Report Screens"]
        end

        subgraph Control["Control Layer"]
            AccountController["Account Controller"]
            ProfileController["Profile Controller"]
            ScreeningController["Screening Controller"]
            ResultsController["Results Controller"]
            GameController["Game Session Controller"]
        end

        subgraph Services["Service Layer"]
            AccountService["Account Service"]
            UserRecordService["User Record Service"]
            AudioService["Audio Recording Service"]
            SpeechClient["Speech Assessment Client"]
            PlanClient["Practice Plan Client"]
            LocalStore["Local Practice Plan Store"]
        end

        subgraph Models["Data and Domain Layer"]
            ParentModel["Parent Account Model"]
            ChildModel["Child Profile Model"]
            SpeechProfile["Speech Profile Model"]
            LearningModule["Learning Module Model"]
            LearningReport["Learning Report Model"]
            GameResult["Game Result Model"]
        end
    end

    subgraph Online["Backend Services"]
        SpeechService["Speech Assessment Service"]
        PlanService["Adaptive Practice Plan Service"]
    end

    View --> Control
    Control --> Services
    Control --> Models
    SpeechClient --> SpeechService
    PlanClient --> PlanService
    LocalStore --> GameUI
```

Figure 3. Software Architecture

## Class Diagram

Figure 4 presents the class diagram of Voice Voyage. It shows the major classes used to manage account access, child profiles, speech screening, learning results, and gameplay. Controller classes coordinate the application flow, service classes perform specific operations, and model classes represent the records used by the system.

```mermaid
classDiagram
    class AccountController
    class ProfileController
    class ScreeningController
    class ResultsController
    class GameSessionController
    class AccountService
    class UserRecordService
    class AudioRecordingService
    class SpeechAssessmentClient
    class PracticePlanClient
    class LocalPracticePlanStore
    class ParentAccount
    class ChildProfile
    class SpeechProfile
    class LearningModule
    class LearningReport
    class GameResult

    AccountController --> AccountService
    AccountController --> ParentAccount
    ProfileController --> UserRecordService
    ProfileController --> ChildProfile
    ScreeningController --> AudioRecordingService
    ScreeningController --> SpeechAssessmentClient
    ResultsController --> SpeechProfile
    ResultsController --> PracticePlanClient
    ResultsController --> LocalPracticePlanStore
    GameSessionController --> LocalPracticePlanStore
    GameSessionController --> SpeechAssessmentClient
    GameSessionController --> GameResult
    ChildProfile --> SpeechProfile
    ChildProfile --> LearningReport
    LearningModule --> GameResult
```

Figure 4. Class Diagram

## Use Case Diagram

Figure 5 illustrates the use case diagram of Voice Voyage. The Parent can create an account, manage the child profile, start screening, view progress, and review learning reports. The Child can complete speech screening and play practice activities. The system supports these actions by checking speech, generating practice plans, saving progress, and displaying feedback.

```mermaid
flowchart LR
    Parent["Parent / Guardian"]
    Child["Child Learner"]

    subgraph System["Voice Voyage System"]
        UC1["Create or Sign in Account"]
        UC2["Manage Child Profile"]
        UC3["Start Speech Screening"]
        UC4["Record Target Words"]
        UC5["Check Pronunciation"]
        UC6["Generate Practice Plan"]
        UC7["Play Practice Activities"]
        UC8["Save Progress"]
        UC9["View Learning Report"]
    end

    Parent --> UC1
    Parent --> UC2
    Parent --> UC3
    Parent --> UC9
    Child --> UC4
    Child --> UC7
    UC3 --> UC4
    UC4 --> UC5
    UC5 --> UC6
    UC6 --> UC7
    UC7 --> UC8
    UC8 --> UC9
```

Figure 5. Use Case Diagram

## Sequence Diagram

Figure 6 shows how the parent sign-up and child screening process occurs in Voice Voyage. The parent enters account and child information, the system confirms the account, and the child completes the screening activity. The application sends the child's recorded speech to the assessment service, saves the results, requests a practice plan, and stores the child profile for future use.

```mermaid
sequenceDiagram
    actor User as Parent and Child
    participant App as Voice Voyage App
    participant Login as Account Login
    participant Speech as Speech Assessment Service
    participant Plan as Practice Plan Service
    participant Local as Local Storage
    participant Cloud as Saved Records

    User->>App: Enter parent and child information
    App->>Login: Create or verify account
    Login-->>App: Account confirmed
    User->>App: Complete screening words
    App->>Speech: Send recorded speech
    Speech-->>App: Return score and speech findings
    App->>Local: Save screening findings
    App->>Plan: Request adaptive practice plan
    Plan-->>App: Return practice activities
    App->>Local: Save latest practice plan
    App->>Cloud: Save child profile and speech summary
    App-->>User: Display learning map
```

Figure 6. Parent Sign-up and Child Screening Sequence Diagram

Figure 7 shows how the speech assessment process works when the child records a target word. The application sends the target word, child age, and audio recording to the speech assessment service. The service checks if the recording is clear, compares it with the target pronunciation, prepares a score, and returns the result to the application.

```mermaid
sequenceDiagram
    participant App as Voice Voyage App
    participant Speech as Speech Assessment Service
    participant Audio as Audio Quality Check
    participant Model as Speech Recognition Model
    participant Result as Result Builder

    App->>Speech: Send target word, child age, and recording
    Speech->>Audio: Check recording quality
    Audio-->>Speech: Return usable audio
    Speech->>Model: Compare with target pronunciation
    Model-->>Speech: Return sound-level match result
    Speech->>Result: Prepare score and findings
    Result-->>App: Return assessment result
```

Figure 7. Speech Assessment Sequence Diagram

Figure 8 presents how Voice Voyage generates an adaptive practice plan. The application sends the child's age and detected speech needs to the practice plan service. The service selects suitable word lists and learning guides, uses an AI helper when available, validates the selected activities, and returns the practice plan to the application.

```mermaid
sequenceDiagram
    participant App as Voice Voyage App
    participant Plan as Practice Plan Service
    participant Guides as Word Lists and Learning Guides
    participant AI as AI Helper

    App->>Plan: Send child age and detected speech needs
    Plan->>Guides: Select suitable guide and word list
    alt AI helper is available
        Plan->>AI: Request practice recommendations
        AI-->>Plan: Return suggested activities
    else AI helper is unavailable
        Plan->>Plan: Select activities using system rules
    end
    Plan->>Guides: Validate selected words and activities
    Plan-->>App: Return adaptive practice plan
```

Figure 8. Adaptive Practice Plan Sequence Diagram

Figure 9 illustrates how gameplay uses the generated practice plan. The child starts a practice level, the application loads the latest practice plan, and the child completes the game task. If speech checking is required, the application sends the recording to the speech assessment service. The system then saves the result and updates the child's progress.

```mermaid
sequenceDiagram
    actor Child
    participant App as Voice Voyage App
    participant Local as Local Storage
    participant Plan as Practice Plan Service
    participant Speech as Speech Assessment Service
    participant Cloud as Saved Records

    Child->>App: Start practice level
    App->>Local: Load latest practice plan
    opt Practice plan is missing but findings are saved
        App->>Plan: Request practice plan again
        Plan-->>App: Return practice plan
    end
    Child->>App: Complete game task or say target word
    App->>Speech: Send recording when needed
    Speech-->>App: Return score
    App->>Cloud: Save level result and progress
```

Figure 9. Gameplay Assessment Sequence Diagram

## Flowchart Diagram

Figure 10 shows the speech screening flowchart of Voice Voyage. The process starts when the parent or child opens the screening activity. The system presents a target word, records the child's speech, checks the pronunciation, and decides whether the recording is usable. If the recording is unclear, the child records again. If all screening words are completed, the system prepares the results and requests the adaptive practice plan.

```mermaid
flowchart TD
    Start([Start Speech Screening])
    Prompt["Show and Play Target Word"]
    Record["Record Child's Speech"]
    Assess["Check Pronunciation"]
    Usable{"Is the recording usable?"}
    Retry["Ask Child to Record Again"]
    MoreWords{"Are there more words?"}
    Results["Prepare Screening Results"]
    Plan["Generate Adaptive Practice Plan"]
    Save["Save Speech Summary"]
    End([Proceed to Learning Map])

    Start --> Prompt --> Record --> Assess --> Usable
    Usable -- "No" --> Retry --> Record
    Usable -- "Yes" --> MoreWords
    MoreWords -- "Yes" --> Prompt
    MoreWords -- "No" --> Results --> Plan --> Save --> End
```

Figure 10. Speech Screening Flowchart Diagram

Figure 11 shows the practice gameplay flowchart of Voice Voyage. The child starts a practice activity, the system loads the latest practice plan, presents a target, checks the child's response when needed, and saves the result. If the child does not meet the required performance, the system allows another attempt before continuing.

```mermaid
flowchart TD
    Start([Start Practice Activity])
    LoadPlan["Load Latest Practice Plan"]
    Target["Present Practice Target"]
    Respond["Child Responds or Speaks"]
    Check["Check Activity Result"]
    Passed{"Target completed?"}
    Retry["Try Target Again"]
    MoreTargets{"More targets in level?"}
    Save["Save Level Progress"]
    Report["Update Learning Report"]
    End([Return to Learning Map])

    Start --> LoadPlan --> Target --> Respond --> Check --> Passed
    Passed -- "No" --> Retry --> Respond
    Passed -- "Yes" --> MoreTargets
    MoreTargets -- "Yes" --> Target
    MoreTargets -- "No" --> Save --> Report --> End
```

Figure 11. Practice Gameplay Flowchart Diagram

Figure 12 illustrates the error handling flowchart of Voice Voyage. The system checks whether the problem is caused by unclear audio, connection failure, or service unavailability. Audio problems lead to re-recording, while service problems may be retried. If the problem continues, the system shows a clear message and uses saved or built-in practice content when possible.

```mermaid
flowchart TD
    Record["Record Speech"]
    Send["Send Recording"]
    Check["Check Result"]
    Success{"Successful result?"}
    AudioIssue["Audio is too quiet,\nunclear, or incomplete"]
    ServiceIssue["Connection or\nservice problem"]
    RetryAudio["Record Again"]
    RetryService{"Can retry request?"}
    Wait["Wait Briefly"]
    UseResult["Use Score and Findings"]
    Fallback["Use Saved or Built-in\nPractice Content"]
    Error["Show Error Message"]

    Record --> Send --> Check --> Success
    Success -- "Yes" --> UseResult
    Success -- "No: audio issue" --> AudioIssue --> RetryAudio --> Record
    Success -- "No: service issue" --> ServiceIssue --> RetryService
    RetryService -- "Yes" --> Wait --> Send
    RetryService -- "No" --> Fallback --> Error
```

Figure 12. Error Handling Flowchart Diagram

## Entity Relationship Diagram

Figure 13 models the main records used by Voice Voyage. A parent account owns a parent record, and a parent record can manage one or more child profiles. Each child profile may have a speech profile, learning progress entries, and a learning report. This structure supports profile management, speech screening, adaptive practice, and progress monitoring.

```mermaid
erDiagram
    PARENT_ACCOUNT ||--|| PARENT_RECORD : owns
    PARENT_RECORD ||--o{ CHILD_PROFILE : manages
    CHILD_PROFILE ||--o| SPEECH_PROFILE : contains
    CHILD_PROFILE ||--o{ LEARNING_PROGRESS : records
    CHILD_PROFILE ||--o| LEARNING_REPORT : summarizes

    PARENT_ACCOUNT {
        string accountId
        string email
        string loginProvider
    }

    PARENT_RECORD {
        string parentId
        string parentName
        string relationshipToChild
        string activeChildId
        timestamp createdAt
        timestamp updatedAt
    }

    CHILD_PROFILE {
        string childId
        string childName
        number age
        string profileImage
        timestamp createdAt
        timestamp updatedAt
    }

    SPEECH_PROFILE {
        string primaryTarget
        string secondaryTarget
        array detectedSpeechNeeds
        array approvedPracticeWords
        number averageAccuracy
    }

    LEARNING_PROGRESS {
        number levelIndex
        number activityIndex
        number accuracy
        timestamp completedAt
    }

    LEARNING_REPORT {
        number completedLevels
        number latestAccuracy
        string progressSummary
    }
```

Figure 13. Entity Relationship Diagram

## Data Flow Diagram

Figure 14 shows the data flow of Voice Voyage from speech screening to practice and reporting. The child provides speech input during screening, the application sends the recording for assessment, and the returned findings are used to form the child's speech profile. These findings are then used to generate the adaptive practice plan. During gameplay, completed activities update the child's progress and learning report.

```mermaid
flowchart LR
    Child["Child Learner"]
    Parent["Parent / Guardian"]
    App["Voice Voyage App"]
    SpeechService["Speech Assessment Service"]
    PlanService["Practice Plan Service"]
    LocalStore[("Latest Practice Plan\non Device")]
    CloudStore[("Firebase Records")]
    Report["Learning Report"]

    Child -->|"spoken words"| App
    Parent -->|"profile details"| App
    App -->|"target word, age,\nand recording"| SpeechService
    SpeechService -->|"score and findings"| App
    App -->|"speech needs and age"| PlanService
    PlanService -->|"adaptive practice plan"| App
    App --> LocalStore
    LocalStore -->|"practice targets"| App
    App -->|"profile, speech summary,\nand progress"| CloudStore
    CloudStore --> Report
    Report -->|"view progress"| Parent
```

Figure 14. Data Flow Diagram

## Access Control Diagram

Figure 15 illustrates the access control design used to protect parent and child records. A parent must be signed in before opening or saving data. The system then checks whether the requested child profile or learning record belongs to the signed-in parent account. If the record does not belong to the account, access is denied.

```mermaid
flowchart TD
    Request["Request to Read or Save Data"]
    SignedIn{"Is the parent signed in?"}
    MatchAccount{"Does the record belong\nto the signed-in parent?"}
    ValidData{"Is the submitted data valid?"}
    AllowRead["Allow Record Access"]
    AllowWrite["Allow Save or Update"]
    Deny["Deny Request"]

    Request --> SignedIn
    SignedIn -- "No" --> Deny
    SignedIn -- "Yes" --> MatchAccount
    MatchAccount -- "No" --> Deny
    MatchAccount -- "Yes" --> ValidData
    ValidData -- "Read request" --> AllowRead
    ValidData -- "Valid write request" --> AllowWrite
    ValidData -- "Invalid write request" --> Deny
```

Figure 15. Access Control Diagram

## Deployment Diagram

Figure 16 presents the deployment design of Voice Voyage. The mobile application can be installed or tested on a user device, while Firebase provides cloud-based login and record storage. The speech assessment service and adaptive practice plan service are prepared as separate backend services so that each part can be tested locally and later hosted online.

```mermaid
flowchart TB
    subgraph Device["User Device"]
        MobileApp["Voice Voyage Mobile App"]
    end

    subgraph Firebase["Firebase Cloud"]
        Auth["Authentication"]
        Firestore["Cloud Firestore"]
    end

    subgraph BackendHost["Backend Hosting Environment"]
        SpeechAPI["Speech Assessment API"]
        PlanAPI["Practice Plan API"]
    end

    subgraph DevSetup["Development and Deployment Files"]
        Docker["Docker Build Files"]
        Railway["Railway Configuration"]
        HF["Hugging Face Deployment Files"]
    end

    MobileApp --> Auth
    MobileApp --> Firestore
    MobileApp --> SpeechAPI
    MobileApp --> PlanAPI
    Docker --> SpeechAPI
    Docker --> PlanAPI
    Railway --> BackendHost
    HF --> BackendHost
```

Figure 16. Deployment Diagram

## Testing and Evaluation Flow Diagram

Figure 17 shows the testing and evaluation flow for Voice Voyage. The researchers check core functions such as account access, child profile management, speech screening, adaptive practice generation, gameplay, and learning reports. After functional testing, the system can be evaluated by intended users and technical evaluators using usability and software quality criteria.

```mermaid
flowchart TD
    Start([Start System Testing])
    Functional["Functional Testing\nCheck major app features"]
    Speech["Speech Assessment Testing\nCheck recording and scoring flow"]
    Content["Adaptive Content Testing\nCheck generated practice plan"]
    Game["Gameplay Testing\nCheck activities and progress saving"]
    Usability["Usability Evaluation\nParents, teachers, or specialists"]
    Quality["Technical Quality Evaluation\nIT evaluators"]
    Analyze["Analyze Results"]
    Improve["Apply Revisions"]
    End([Finalize System])

    Start --> Functional --> Speech --> Content --> Game
    Game --> Usability
    Game --> Quality
    Usability --> Analyze
    Quality --> Analyze
    Analyze --> Improve --> End
```

Figure 17. Testing and Evaluation Flow Diagram

## Methodology

Figure 18 shows the Agile Software Development Life Cycle used for the development of Voice Voyage. The process begins with planning the system requirements, followed by interface and system design, development of the application and backend services, testing of major functions, deployment preparation, and review based on feedback and evaluation results.

```mermaid
flowchart LR
    Planning["Planning\nDefine objectives, users,\nand requirements"]
    Design["Design\nPrepare screens, database,\nand system diagrams"]
    Development["Development\nBuild app features and\nbackend services"]
    Testing["Testing\nCheck screening, gameplay,\nand reports"]
    Deployment["Deployment\nPrepare local and hosted\nservice setup"]
    Review["Review\nCollect feedback and\nimprove the system"]

    Planning --> Design --> Development --> Testing --> Deployment --> Review
    Review --> Planning
```

Figure 18. SDLC Agile Model
