# KBC LearningOS — Help Knowledge Base

Source: the current LMS code (`main`, commit `629083d4`, 13 Oct 2026). Quoted text is the exact wording shown in the app.

## How to use this document (instructions for the assistant)

- Answer from this document only. If something is not covered, say so and suggest contacting the programme team, coach or an administrator.
- Some pages exist but show **sample (demo) data**, not real data. Never describe their contents as fact. See [Not live yet](#not-live-yet).
- Never ask a user for their password, and never promise an outcome (a grade, an approval, an account change) that only staff can give.
- Routes (e.g. `/learner/calendar`) are the page addresses in the web app.

---

## 1. What the LMS is

**KBC LearningOS** is Kent Business College's apprenticeship platform. It covers the apprentice journey in one place: enrolment → programme and curriculum → learning → evidence and assessment → coaching and reviews → gateway readiness.

**Structure of learning:** Programme → Cohort → Group → Module → Week → Component. A component is one activity: video, podcast/audio, reading, PowerPoint, quiz, assignment, reflection, live Teams session, checkpoint quiz, monthly KSB quiz or coaching preparation.

**Main programmes:**
- Marketing Executive (ME)
- Marketing Manager (MM, Level 6)
- Project Controls Professional (PCP, Level 6)
- Associate Project Manager (APM)

### Who uses it

| User | What they do |
|---|---|
| Learner (apprentice) | Studies, takes quizzes, submits assignments and evidence, books and signs coaching meetings and reviews, tracks hours and KSBs |
| Coach | Manages a caseload: monthly coaching, progress reviews, catch-ups, attendance, marking, monthly log sign-off |
| Tutor | Teaching groups and live sessions |
| Employer | Follows their apprentices and signs reviews and agreements |
| Curriculum | Designs programmes, modules, weeks, quizzes and the book Knowledge Base |
| Enrolment | Creates learners and runs the enrolment flow |
| Engagement | Points, rewards, events, clubs, flash cards, attendance risk |
| Audit / Quality | Audit workspace and sign-off reports |
| Super Admin | Accounts, access, platform settings |

---

## 2. Signing in and accounts (everyone)

### Sign in (`/login`)
1. Enter your email and password.
2. Optionally turn on **Remember me** ("Stay signed in on this device. Leave it off and closing your browser signs you out.").
3. Click **Sign in to Workspace**. You can also use the Microsoft button.

### Sign-in errors

| Message | Meaning |
|---|---|
| "Incorrect email or password" | The email or password is wrong. The same message is used for both. |
| "Too many failed attempts. This account is locked for N minute(s)." / "This account is temporarily locked after too many failed attempts…" | After 5 failures the account locks. The lock starts at 5 minutes and rises to a maximum of 60. Wait, or reset your password. |
| "Too many failed attempts from this location. Try again later." | More than 20 failures from one network in 15 minutes. |
| "Choose your own password to finish signing in." | A new learner used the first-sign-in password and must set their own. |
| "Microsoft sign-in is not configured." | Server setup issue. Contact an admin. |

### Forgot or set a password (`/forgot-password`)
1. Click **Forgot password?** and enter your email.
2. You will see "If that address is registered, we have emailed it a link…"
   - A reset link works once and expires in **1 hour**.
   - A new-learner set-password link expires in **7 days**.
   - At most 3 reset emails per address every 15 minutes.
   - Nothing arrived after a few minutes? Check your junk or spam folder.

**Password rules:**
- 8–128 characters
- Not a common password
- Not a single repeated character
- Must not contain your email address or your name
- Not the first-sign-in password
- Both entries must match

### How long a session lasts
- **Normal:** you are signed out after 5 hours of inactivity, and after 7 days at most.
- **Remember me:** 14 days of inactivity, 90 days at most.
- **Signing out** in one tab signs out your other open tabs too.

### Session and access messages

| Message | Meaning / what to do |
|---|---|
| "Your session has ended" / "Please sign in again to continue." | Your session really ended. Sign in again. |
| "The sign-in service is temporarily unavailable." | A short server or database problem. You are **not** signed out. Wait a few seconds and retry. |
| "You do not have permission to perform this action." | Your account lacks the access level needed. |
| "This page is not available for your account" | Ask an administrator if you think you should have access. |
| "You don't have access yet" (`/access-required`) | A staff account with no access level. Click **Request access**; the admin is emailed (once per 30 min). Access works straight away once granted, with no need to sign in again. |
| "Could not load your session" | Check your connection and click **Try again**. |

### More than one role
**Choose your workspace** (`/choose-workspace`) lets you pick where to start. You can switch at any time without signing in again.

---

## 3. Learners

### 3.1 Before you can start learning
Some checks may stop you reaching your programme:

1. **Onboarding (new apprentices):**
   - Welcome form (`/learner/welcome`): address, UK postcode, mobile, date of birth, then your signature (drawn, or a PNG/JPEG/WebP under 5 MB).
   - Then the enrolment wizard (`/learner/onboarding`).
   - When submitted: "Enrolment submitted — … sent to the team for review."
2. **Four enrolment reviews** (`/learner/onboarding/reviews`). They open after the enrolment is submitted, and are booked with your case owner on weekdays (not bank holidays):
   - Eligibility Review & FS Discussion
   - RPL And Experience
   - Workplace Health & Safety Declaration
   - ULN Privacy Notice & Learner Acknowledgement

   When all four are signed, you move on automatically. Commercial learners skip these.
3. **Compliance documents** (`/learner/compliance-documents`): Apprenticeship Agreement, Commitment Statement / training plan, employer–provider agreement and Individual Learner Record. Some are signed by typing your name.
4. **Previous learning record:** if you see "Review and sign your previous learning record", click **Review and sign** and sign the listed months.
5. **First session:** **Book my first session** with your case owner. The earliest day is tomorrow (UK time). Your programme opens after this session.
6. **Cohort start date:** before your cohort starts you can view your programme but not complete learning: "Learning activities open on {date}…". You can save drafts. If you see "Your cohort start date must be confirmed…", contact your programme team.

### 3.2 Home and menu
- **Home** (`/learner/home`):
  - This week's learning
  - OTJ progress card (planned against completed hours)
  - Quick links: book monthly coaching, report absence, Inclusion & Safeguarding
  - Notifications bell, help, password reset
- **Menu, in order, exactly as it appears:**
  1. **Home** (`/learner/home`)
  2. **Dashboard** (`/learner/dashboard`) — see 3.15a for the tools reached from here, not from the main menu
  3. **My Learning** (`/learner/my-learning`) — the **Learning Plan** (`/learner/learning-plan`) is reached from inside My Learning, not its own menu item
  4. **My Progress** — a group, not a page of its own. Opening it expands five items:
     - Monthly Submission (`/learner/monthly-submission`)
     - Monthly Logs (`/learner/monthly-logs`) — the **Monthly Cycle** view (`/learner/monthly-cycle`) is the same section under a second address; see 3.9a
     - Monthly Coaching Meeting (`/learner/monthly-coaching`)
     - Progress Review (`/learner/progress-reviews`)
     - Reviews (`/learner/reviews`) — see 3.10a for how this differs from Progress Review
  5. **Attendance** (`/learner/attendance`) — reporting an absence is a button inside this page, not a separate menu item
  6. **Evidence** (`/learner/evidence`)
  7. **Calendar** (`/learner/calendar`)
  8. **My Enrolment** (`/learner/onboarding`)
  9. **Compliance documents** (`/learner/compliance-documents`)

  **Messages** does not currently appear in the menu — the college has chat switched off college-wide. Opening `/learner/messages` directly redirects back to Home. Do not tell a learner to message their coach through the portal; point them to the contact details on their Profile page, or to their coach/tutor directly.

### 3.3 My Learning (`/learner/my-learning`)
- **Tabs:** Modules, Quizzes, Assignments. Switch between **My courses** and **Free courses**.
- **To open an activity:** pick a module, then a week on the timeline, then **Open activity**.
- **Nothing is locked week by week.** You can open anything at any time; only the cohort start date restricts you.
- **Free courses** do not count towards programme hours or progress.
- **Module certificate:** **Get certificate** appears once you meet the module's completion %, pass the final quiz if one is required, and a certificate template exists.
- **Learning Plan** (`/learner/learning-plan`) is reached from inside My Learning, not from its own menu item — it is the roadmap view of your modules and milestones across the whole programme.

### 3.4 Videos, readings, podcasts, slides
1. Open the activity. A timer runs only while the page is visible; skipping through a video does not add time.
2. If evidence is required, upload at least one file.
3. Click **Finish**. It stays locked until the criteria are met.
4. Choose **Yes, add reflection** or **No, finish without reflection**. Some activities require a reflection.
5. You'll see "Completed · {time}" and **Next activity**.

Other tools on these pages:
- **Manual time:** you may correct the time (hours and minutes). With two attempts you choose one time; they are not added together.
- **Reading tools:** dyslexia-friendly font, highlights (kept on this device only), read aloud, download as PDF.
- **Coach verdicts:**
  - *Pending coach review*: wait for your coach.
  - *Accepted*: nothing more is needed.
  - *Rejected*: read the feedback and submit again.

### 3.5 Quizzes
**How to take one:**
1. The intro screen shows the time limit, passing grade, number of questions and points. Click **Start Quiz**.
2. **Do not refresh or close the page.** Your answers will be lost and the quiz restarts.
3. If the quiz has a time limit, it submits automatically when time runs out.

**Question types:** single choice, true/false, multiple answer, ordering, matching, image matching, fill the gap, keywords.

**Grading:**
- Score = points earned ÷ points possible.
- You pass at or above the passing grade (the usual default is **70%**).
- Every attempt is kept.
- **Retake Quiz** is available; your previous result stays saved.
- A passed quiz stays passed even if a later retake fails.

**Results:** Passed or Not Passed, grade, score, time taken, and a per-question breakdown of your answer and the correct answer.

**Points:** earned only for passing on the **first attempt**. Retakes earn nothing.

**Errors:**
- "This quiz has no questions yet." means contact your tutor.
- "This quiz has changed. Reload it before submitting…" means reload the page.

**AI personalised reading:** after a quiz, the AI writes reading on the areas you got wrong.
1. Click **Open Reading & Start Time**.
2. Read the material.
3. Click **Finish Reading & Add Actual Time**.
4. Confirm the timer, or type the minutes.

The reading time is added to your off-the-job hours.

### 3.6 Working-hours rule when you finish or submit
- Official hours are **Monday–Friday, 07:00–19:00 UK time**, excluding bank holidays.
- You can study at any time. The rule is only checked when you press Finish or Submit outside those hours.
- If it is outside hours, a dialog asks for the actual date and time you did the work, then **Final Submit**. Out-of-hours times are still accepted, with a warning.
- Future times are refused.
- Your answers are kept, so this does not use a retake.

### 3.7 Reflections
The tabs are Learning, KSBs, Apply, Evidence, Benefit, OTJH and Review. All of these are needed before **Submit for tutor review**:
- A reflection of at least 100 words
- KSBs selected and rated
- Workplace application
- Employer benefit
- OTJH confirmation
- Your declaration

You can use voice recording and **Proofread & improve my wording** (AI). **Save draft** is always available.

### 3.8 Monthly Submission (assignments) (`/learner/monthly-submission`)
The 8-step monthly assignment:
1. Answer
2. Evidence
3. KSBs & hours
4. Full-month reflection
5. Impact & employer benefit
6. Action plan & EPA
7. Coaching & presentation
8. Quality checks

Main rules:
- The answer must be at least 120 words. Most other texts need at least 20 words, and each claimed KSB needs a 20-word explanation.
- Hours: a maximum of **8 hours per day** across all assignments, on working days within the assignment month.
- A coaching meeting must be booked between the last 10 days of the month and the 5th of the next month.
- The MCM PowerPoint must be uploaded or generated.

**Next** lists anything missing. **Save draft** works at any time.

**Extra activities:** learning done outside working hours. The description needs at least 120 words, and you must tick "I confirm this learning took place outside my working hours."

### 3.9 Monthly Logs (`/learner/monthly-logs`)
- An automatic monthly record of your activities and hours.
- **Signing opens after the month ends.**
- Once both the learner and coach have signed, the log locks. You can also sign it from the Monthly Coaching Meeting form.

### 3.9a Monthly Cycle (`/learner/monthly-cycle`)
- The same section as Monthly Logs, reached by a second address — the menu's "Monthly Logs" link can land you here.
- A month picker and a filter across five activity types: **Quizzes**, **Videos**, **Learning** (readings, podcasts, reflections, uploaded resources), **Coaching** and **Reviews**.
- Only shows what has **already happened** in the selected month — sessions still to come, or cancelled ones, are not listed here.
- Includes the monthly report: generate or download it as a PDF, and open any attachment that was submitted with it.

### 3.10 Coaching meetings and reviews
- **Monthly Coaching Meeting (MCM)** (`/learner/monthly-coaching`):
  - Shows your current meeting, items that need your signature, and history.
  - Your coach completes the form first ("The coach must complete this review before you can sign it."). Then you **Review & sign** with a saved or newly drawn signature.
- **Progress Review** (`/learner/progress-reviews`): join, reschedule, view details, and record your attendance.
- **Booking rules (all meetings):**
  - No weekends.
  - No UK bank holidays.
  - No past dates.
  - No clashes with other meetings.

  You can connect your Microsoft or Google calendar so only your busy times are checked.

### 3.10a Reviews — how the three review features differ
Three separate menu items sound alike. Use the right one:
- **Monthly Coaching Meeting** (`/learner/monthly-coaching`) — the recurring monthly 1:1 with your coach.
- **Progress Review** (`/learner/progress-reviews`) — the formal, less frequent review with your coach **and employer** together. It includes a review-areas dashboard (attendance, OTJH, KSB progress, module progress, quizzes, evidence, workplace practice, English/maths, behaviour, safeguarding), a safeguarding section, and sign-off once your coach has prepared it.
- **Reviews** (`/learner/reviews`) — the record of review **sessions already booked or held**, including any reviews imported from the college's previous system. Use this to look back at what was discussed and signed, not to book a new one.

A learner who was never told which of these contains what is the most common source of confusion — when in doubt, ask whether they mean the monthly 1:1, the formal review with their employer present, or something from before this platform was introduced.

### 3.11 Calendar (`/learner/calendar`)
- Shows all your sessions, coaching, reviews and events. Event types include Live Session, Coaching and Review, each shown in its own colour.
- **Views:** switch between **Month**, **Week** and **Day** using the buttons at the top.
- **Click any event** to open its details. For a live session this shows a **Join Meeting** button (opens the meeting link directly) and an **Export .ics** button to add that one event to your own calendar app — there is no single button that exports everything at once.
- **Book a Coach Session:** Catch-up, Student Support, PR, MCM, Gateway or Other.
- **Catch-ups:** you can change or cancel them up to **12 hours** before the start.
- "No coach has been assigned to you yet" means contact your programme team.

### 3.12 Attendance and absence (`/learner/attendance`)
- **Join** opens 15 minutes before a lecture and stays open until it ends. If a learner says they joined but the session still shows as not attended, the most likely cause is that they opened the link outside that window — the system only credits attendance for the open period, not for watching the recording afterwards.
- **Reporting an absence is a button inside the Attendance page itself**, not a separate menu item. (`/learner/report-absence` still works as a direct link for anyone with it bookmarked, but it is not how learners are meant to reach it.)
  1. Choose the lecture.
  2. Choose the reason.
  3. Choose a catch-up route: watch the recording, join another group, or book a coach catch-up.
  4. Optionally add evidence (JPG, PNG or PDF, up to 10 MB).
  5. Click **Book catch-up & submit**. The report goes to your coach and tutor — this is a real, saved submission.
- **Booking a catch-up session** (after an absence report) is also done from inside Attendance, via the "Book Catchup Session" dialog — again a real, saved booking.
- **Catch-up must be completed within 7 days.** Watching a recording does not change live attendance by itself — your coach approves the catch-up to restore it.
- **Repeated absence:**
  - 1 missed session: catch up within 7 days.
  - 2 missed sessions: a support plan is made and your line manager is informed.
  - Repeated absence: a formal review with your employer.

**Do not confuse this with the separate "Catch-Up Learning Hub" page (`/learner/catchup`).** That page is a demonstration only: its "Submit Catch-Up Evidence" form shows a success message but does not save anything or reach the coach. If a learner mentions submitting catch-up evidence and nothing seems to have happened, this is very likely why — point them to the real flow above, inside Attendance, instead.

### 3.13 Hours (OTJH) and KSBs (`/learner/otjh`, `/learner/ksbs`)
Both addresses open the same page as **My Progress → Overview** (`/learner/progress`), just starting on a different tab — they are not separate pages. Neither has its own entry in the main menu; learners usually reach them from a card on Home or This Week rather than by typing the address.
- **OTJ Hours:**
  - Shows your hours against target, an activity log, and a breakdown by activity type.
  - Hours come from videos, readings, quizzes (including AI reading), assignments and attendance.
  - Assignment hours count only after tutor review.
- **KSBs:** your points against the total for each KSB.

### 3.14 Evidence (`/learner/evidence`)
- Upload PDF, Word, PowerPoint, PNG, JPG or MP4 files up to **50 MB**. Map each to a week, module and KSBs, with a description of up to 500 characters.
- **Statuses:** Submitted/Pending, Validated (Accepted), Needs work (Referred).
- You can delete your own uploads, but not historical records.

### 3.15 Rewards and community
- **Points:**
  - Earned for passing a quiz on the first attempt.
  - Earned for the first view of a recording, PDF, PowerPoint or podcast.
  - Earned for verified attendance and approved evidence.
- **Rewards shop** (`/learner/rewards`): claiming reserves your points and sends the claim for review.
- **Clubs** (`/learner/clubs`, assigned by your coach), **Events** (`/learner/clubs/events` — book or cancel), and **Flash cards** (`/learner/flash-cards`) for your programme.

### 3.15a Where to find Clubs, Events, Rewards and Flash cards
These four do **not** appear in the main learner menu. They are reached from the **Dashboard** (`/learner/dashboard`), not Home — if a learner is looking at Home and cannot find them, point them to Dashboard first, then the tool.

### 3.15b Profile (`/learner/profile`)
Not in the main menu either. Shows personal details, programme information, employer details, and your coach and tutor's contact details — the place to send a learner who wants to message their coach while chat is switched off college-wide (see 3.2).

### 3.16 Mobile app (KBC Learn, Android)
- **Sign-in:** use your LMS email and password. Password resets are done on the website.
- **Contents:** only audio, video and choice quizzes. Assignments, documents and live sessions stay on the website.
- **How it works:**
  - The quiz pass mark is 70%.
  - You can answer by voice ("option B").
  - A reflection is required to finish an activity.
  - Drafts are kept on the phone if a save fails.
- **Reminders and hours:**
  - Meeting reminders arrive 15 minutes before a meeting.
  - The weekly aim is 9–10 hours.
  - Joining a meeting does not by itself record attendance.

---

## 4. Curriculum team

### 4.1 Where things are
- **Library** (`/curriculum/library`):
  - Free Courses
  - Week Templates
  - Review Templates
  - KSB Standards
  - KSB Frameworks
  - Quiz Workspace
  - Knowledge Base
  - Question Bank
- **Delivery** (`/curriculum/delivery`): Cohorts, Groups, Module Builder, Teams Meetings, Recordings, Bank Holidays, Session Calendar.
- **Quality** (`/curriculum/quality`): gap counters such as "Groups without a coach", "Modules without KSB mappings" and "Modules not yet published", plus the Audit Trail.

### 4.2 Programmes (`/curriculum/programmes`)
- Edit programme details and funding fields.
- **Apply KSB Source** sets the standard or framework that coverage is measured against.
- You can see enrolled learners' hours and KSBs. Cohorts, groups and modules are managed in the structure editor.
- **Archive a programme:** this keeps its cohorts, groups and modules. To delete it, first remove its linked modules, groups and cohorts.

### 4.3 Module Builder (`/curriculum/module-builder`)
- **Create new module:** create it empty, or pre-create a number of weeks. It is saved as a draft.
- **Weeks:**
  - Add a week, or add weeks from a template.
  - Drag to reorder.
  - Duplicate a week (its live session is copied without the Teams meeting).
- **Components:** set expected OTJH, whether a reflection is required, tutor validation, completion rule and minimum words.
- **KSBs:** choose the KSB source first. Each KSB weight must be positive.
- **Saving:**
  - "Unsaved changes - press Save"
  - "Save failed - your changes are still here"
  - If someone else saved first, you can load their version.
- **Duplicate module:** progress, submissions, attendance and files are never copied.

### 4.4 Week Templates (`/curriculum/week-builder`)
Build a week once, then drop it into any module. Accepted files:
- Reading: Word, PDF, TXT, RTF, ODT
- Podcast: MP3, OGG, WAV, M4A, AAC, WEBM
- Slides: PPT, PPTX, PPS, PPSX or PDF

A live session without a date is not sent to Teams.

### 4.5 Quiz Workspace (`/curriculum/quiz-xml`)
**Statuses:** Draft, Pending (also covers validating), Published, Private, Archive (archived quizzes can be restored or deleted permanently).

**Four ways to create a quiz:**

1. **Add New Quiz:**
   - Fill in title, Programme → Module → Week, version, author and status.
   - Attach an XML, SCORM or Excel/CSV file.
   - Click **Save Quiz**.
2. **Upload Quiz File:** XML, SCORM ZIP, XLSX/XLSM or CSV.
   - **CSV/Excel:** one question per row, headers in row 1.
     - `question` (required)
     - `question_type` (blank = single choice)
     - `option_a` … `option_e`
     - `correct_answer`: a letter (A–E), a number (1–5) or the exact text; several answers as `A,B`
     - `feedback` (optional)
     - Excel files must be `.xlsx` or `.xlsm`, not `.xls`.
   - **SCORM:** a ZIP with `imsmanifest.xml` at the top level.
   - **Errors:**
     - "Unsupported quiz file type…"
     - "File uploaded, but no questions were detected…" (the quiz is saved but marked invalid)
     - "XML parse error…"
     - "Question N: Select a correct answer before learners take this quiz."
3. **Manual Quiz** (`/curriculum/quiz-xml/manual`): write the questions yourself, mark the correct answers, then set learner options (randomize, show correct answer, attempts, retake after pass). Click **Save Manual Quiz**.
4. **Generate Questions (AI Question Generator):**

   | Field | Meaning |
   |---|---|
   | Quiz title | The saved quiz's name |
   | Programme / Module / Week | Where the quiz belongs |
   | Question count | Up to 60 (default 5) |
   | Mixed quiz | AI mixes question formats and balances easy, medium and hard |
   | Topic | What the questions should focus on |
   | Embedded AI prompt / Customize | Instructions for the AI. This is not lesson content. |
   | Lesson content | Pasted text to generate from |
   | Source files | TXT, CSV, XML, Excel, PowerPoint, PDF, DOCX, SCORM ZIP (≤ 50 MB per file; about 60,000 characters are used; scanned PDFs are read up to 24 pages) |

   Steps:
   1. Provide a topic, pasted text or files.
   2. Click **Generate preview**.
   3. Review and edit the questions.
   4. Click **Save as quiz**. It is saved as a **draft**.

   Notes:
   - **Image matching** questions need real images. Without them the AI writes text placeholders such as "Image: TV ad", and no picture is shown.
   - "Add a topic, paste lesson content, or upload source files first." means you gave no content.

**Edit and publish** (`/curriculum/quiz-xml/:quizId/edit`):
- **Settings:** duration, passing grade %, attempts, points cut after retake.
- **Changing status** to Published makes the quiz live.
- **Assigned modules:**
  1. Pick a programme.
  2. Tick the modules.
  3. Choose a week for each.
  4. Click **Save links**.

  **A quiz reaches learners only when it is published and linked to a module week.**

**Checkpoints** (`/curriculum/checkpoints`): monthly checkpoint assessments. These are quizzes listed separately from the Quiz Workspace.

### 4.6 Question Bank (`/curriculum/question-bank`)
- Questions grouped by programme.
- **Add to quiz** copies a question into another quiz of the same programme.
- **Currently used in** shows which quizzes use a question.

### 4.7 Knowledge Base, programme books (`/curriculum/knowledge-base`)
Upload each programme book once. It is processed in the background so questions can be generated from the right chapters.

**Upload:**
1. Click **Upload book**.
2. Choose a PDF (up to 200 MB).
3. Tick the programmes (ME, MM, PCP, APM).
4. Click **Upload**.

A book shared by two programmes is stored once and linked to both.

**Statuses:**
- The normal path is Queued → Extracting → Chunking → Embedding → Verifying → **Ready**.
- **Retrying:** "Will retry automatically."
- **Needs review:** gaps were found. Use **Retry**, or **Accept with gaps**.
- **Failed:** use **Retry**.

**"Processing is paused: the background worker is not running…"** Books stay queued and continue automatically once the worker starts. Ask an administrator.

**Details** shows completeness, and the chapters and sections the book was split into.

---

## 5. Coaches (`/workspace/coach`)

### Dashboard
- **Tiles:** learners, pending marking, MCM/PR/catch-ups this week, OTJH at risk.
- **Upcoming meetings:** reschedule, send a reminder (one per meeting), view the form, generate the presentation.
- **Risk rules:**
  - Attendance: 2 absences in a row is a warning; 3 or more is critical.
  - OTJH: 30 hours behind is a warning; 40 or more is critical.
  - Progress Review: warning after 10 weeks, critical after 12.
  - MCM: warning after 3 weeks, critical after 4.

### Caseload and case file
- **Caseload** (`/coach/caseload`): statuses are On Track, Need Attention, At Risk and On Break. Export to PDF.
- **Learner Case File:** Overview, Progress, Evidence, KSBs, Assignments, Coaching reviews, Attendance, Monthly Focus, historical Aptem assessments.

### Meetings and reviews
- **Monthly Coaching Meetings** (`/coach/monthly-coaching`):
  1. **Schedule meeting** (the Teams meeting is created when you save).
  2. Join the meeting.
  3. Fill in the form, then **Save & Complete MCM**.
  4. Optionally generate an **AI Meeting Summary** from the Teams transcript or an uploaded `.vtt` (up to 5 MB).
- **Progress Reviews** (`/coach/progress-reviews`):
  - Generate slides, or upload your own.
  - Fill in the form, then **Send for signatures**. Answers lock while people sign.
  - Editing a completed review clears all signatures, so everyone signs again.
- **Catch-up Queue / Calendar:**
  - Approve and place learner requests.
  - Schedule catch-ups for missed lectures.
  - A clash shows "This learner is busy at that time."

### Attendance, marking and monthly logs
- **Attendance** (`/coach/attendance`): choose programme, group, session; mark Present or Absent; save.
- **Absence Reports:** approve or decline. A reason is required, and you can notify the learner.
- **Marking** (`/coach/marking-queue`):
  - Review the submission. **Generate AI draft** is optional and only a draft.
  - Then **Accept** or **Refer back**. Feedback is mandatory.
- **Monthly Logs:** sign after month-end. **Unlock monthly log** reopens a locked log and keeps its existing signatures — but this button is **admin-only**; a coach cannot unlock one themselves and should escalate to an admin if a learner needs their log reopened.

### Viewing as an admin
When an admin views a coach's workspace, it is read-only.

---

## 6. Other staff roles

### Tutor (`/workspace/tutor`)
Reached via the **My Teaching** sidebar item. The page itself greets you by name ("Good morning, {name}") and shows your modules and next scheduled session — "My Teaching" is the menu label, not text on the page.

### Enrolment (`/users`)
**Users directory:** search, filter, export.

**Create:**
- **Create user:**
  - Choose Apprenticeship or Commercial learner. This cannot be changed later.
  - Choose employer, case owner and status.
  - An invitation is sent. If the email failed, re-send it or **Copy set-password link**.
- **Import learners:** download the template, fill one learner per row, upload the .xlsx (max 5 MB). First name, Surname and Email are required.

**Programme status:**
- The path is Fresh user → Onboarding → Delivery → Ready to enrol → Active. Withdrawn, On break and Completed are also possible.
- Apprentices move to Delivery automatically when the four onboarding reviews are signed.
- Activation happens automatically when all documents are signed and the start date arrives.

**Learner record:** issue the written agreement and training plan, build the learning plan, withdraw or delete.

**First sessions** (`/users/first-sessions`): learners' first-session bookings.

### Employer (`/employers/<id>`)
- **My learners:**
  - Linked apprentices, with Overview, Learning plan, Monthly logs, KSB progress, Assignments, Documents and Progress reviews.
  - In a progress review, answer the employer questions, then **Sign as employer**. The coach must prepare the review first.
- **All documents:** filters for Awaiting your signature, Waiting on others and Signed.

### Super Admin (`/workspace/admin`)
- **Accounts:**
  - Invite, reset password, suspend, restore, unlock, delete.
  - Grant access levels: Enrolment, Curriculum, Coach, Tutor, Learning record monitoring, Advanced Admin, Super Admin.
- **Logs and reports:** Access Logs, Audit Trail, Email Delivery, System Status, Platform Report (exportable as CSV).
- **Documents, evidence and certificates:** Documents, Evidence portfolio PDFs, Certificate designer.

### Engagement (`/workspace/engagement`)
- **Learners and risk:** engagement scores, attendance risk (critical below 55, high below 70), interventions.
- **Points and rewards:** points rules, rewards shop, voucher claims, recognition.
- **AI or manual flash cards.**
- **Activities:** events, clubs, feedback.

### Audit
- **Auditor workspace:** learner activity, OTJ ledger, monthly timeline, Monthly Learning Sign-Off Report PDF (needs learner and coach signatures).

---

## 7. AI features (summary)

AI only drafts. A person always makes the final decision.

| Feature | Who | What it does |
|---|---|---|
| AI personalised reading | Learner | Reading on the topics you got wrong in a quiz; its time counts towards OTJ |
| Proofread & improve / learning statements | Learner | Improves the wording of reflections and assignment statements |
| KSB explanations, monthly reflection drafts | Learner | Drafts text; nothing is saved automatically |
| AI writing check | Learner and tutors | Advisory flag ("Suspected AI writing — tutor review required"); it is not proof |
| AI Question Generator | Curriculum | Generates quiz questions from a topic, text or files |
| Book Knowledge Base | Curriculum | Processes programme books for question generation |
| AI marking draft | Coach / Tutor | First-draft feedback; the coach decides the mark |
| AI Meeting Summary | Coach | Summarises a Teams transcript into the review form |
| AI flash cards | Engagement | Builds flash-card decks from files |
| Evidence classifier | Audit | Flags evidence uploaded to the wrong place |

---

## 8. Glossary

| Term | Meaning |
|---|---|
| KSB | Knowledge, Skills and Behaviours, from the apprenticeship standard |
| OTJ / OTJH | Off-the-job training hours, the learning time an apprentice must log |
| MCM | Monthly Coaching Meeting |
| PR | Progress Review, the regular learner–employer–provider review |
| Tripartite | A review with the learner, employer and provider |
| Catch-up | A session to make up a missed lecture, within 7 days |
| Gateway | The checkpoint before End-Point Assessment |
| EPA / EPAO | End-Point Assessment / the organisation that carries it out |
| RPL | Recognition of Prior Learning |
| ILR | Individualised Learner Record |
| FS | Functional Skills |
| Checkpoint | A monthly assessment quiz |
| Case owner | The staff member who runs a learner's enrolment and first session |
| Aptem | The previous apprenticeship system; old reviews are shown as "migrated" |
| Cohort / Group | An intake of learners / a teaching group within it |
| Component | One learning activity inside a week |

**Common statuses:**
- **Learner progress:** On Track, Need Attention, At Risk, On Break.
- **Reviews:** Scheduled, Awaiting signature, Completed.
- **Evidence:** Pending, Accepted, Referred.
- **Content:** Draft, Published, Private, Archive.

---

## Not live yet

Do **not** present these as working features:

- **Messages / chat** is switched off. The Messages links are hidden.
- **Sample data only:**
  - Learner Support hub (`/learner/support`)
  - Learner Knowledge Base articles (`/learner/knowledge-base`)
  - Gateway page (`/learner/gateway`)
  - **Catch-Up Learning Hub (`/learner/catchup`)** — its "Submit Catch-Up Evidence" form only shows a fake success screen; nothing is saved or sent anywhere. The real catch-up booking and absence-reporting flow is inside the Attendance page (`/learner/attendance`) — see 3.12.
  - Tasks (`/tasks`)
  - MIS, QA Review Centre, Leadership, Finance, Support, Safeguarding and old Compliance pages
  - The `/employer/*` sidebar pages
- **Curriculum Quality hub cards** marked "coming soon": Published Content, Curriculum Reports, Version Control, KSB Coverage.
- **Book Knowledge Base in the AI Question Generator** (a "Knowledge Base Books" picker and per-question sources), and **renaming a book**. These are built on a feature branch and are **not yet in the main release**. On the live site the generator uses only the topic, pasted text and uploaded files.
