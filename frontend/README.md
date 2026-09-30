# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and Oxlint's TypeScript related rules in your project.

## Learning Material Upload Regression

On `/teacher/upload`, enter `test` as the description and select `image.png`. Confirm the unsupported-file warning appears, then click Upload and verify no POST to `/api/teacher/notes` occurs and no material is created. Replace the image with `valid.pdf`; confirm the error clears and the upload succeeds. Also verify `valid.pdf` plus `invalid.png` rejects the entire selection without uploading, while a description with no attempted attachment still uploads as a text-only material.

## Question Bank Manual Test

After migration 020 has been reviewed and applied by the database operator, sign in as a Teacher assigned to Science and open `/teacher/question-bank`. Download the template, import a valid 30-question CSV, confirm preview reports 30 valid and zero invalid, then import and verify pagination, search, topic, and difficulty filters. Preview a CSV with an invalid difficulty, missing correct option, and duplicate question; import must remain disabled. Create, edit, and delete a question. In Quiz Builder, choose Science, add selected and random bank questions alongside a manual question, verify duplicate and 100-question limits, save and publish, and take the Quiz as a Student. Finally edit and delete a source Bank question and confirm the saved Quiz and its attempt history remain unchanged.

## Quiz Form and History Manual Regression

In a new Quiz, add five Science Question Bank questions while the untouched blank placeholder is present; verify exactly five cards remain. Click `+ Add Question` once and verify exactly one new blank card appears (six cards total). Leave the Quiz title blank and choose `Save as Draft`; verify no request is sent, the inline message reads `Quiz title is required.`, the Toast says `Enter a Quiz title before saving.`, and focus returns to Title. Enter a title, save as Draft, reopen the draft, then publish it. With five Mathematics questions present, change Subject to Science: verify all five cards remain, no confirmation dialog appears, and a warning says to review the kept questions. Open the Bank picker and add Science questions, then switch back to Mathematics and verify the same existing cards remain while Bank/random selection now uses Mathematics. Change Subject with only a pristine blank placeholder and verify there is no warning. Take the published Quiz as a Student, then check Quiz History, attempt details, Teacher View Attempts, and Teacher attempt details. Confirm the Student sees selected answers and Correct/Incorrect/Skipped status without the answer key, the Teacher sees both selected and correct answers, and later Question Bank edits/deletion do not alter saved Quiz snapshots or historical attempts.
