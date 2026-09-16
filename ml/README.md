# Evaluating predictions with school records

From the project root, with the usual virtual environment and MySQL running:

```bash
python -m ml.evaluate_school_outcomes --subject Science
```

This is a read-only diagnostic. It prints aggregate counts and, when enough records exist, the mean absolute error (MAE) in **exam percentage points** for a mean-score baseline and a regularized linear model (Ridge). It never changes the saved Random Forest model, the database, or what teachers and students currently see. A lower MAE on one exam is not sufficient grounds to deploy a model.

The target is a **published Grade 10 terminal paper exam** with recorded marks. A student needs a previously recorded published paper result in the same class and subject to contribute an example. Features include that most recent earlier paper percentage, earlier class lab quiz average and attempt count, and earlier daily attendance rate and number of recorded days. Lab quiz submission time comes from the saved answer records because older databases do not have `quiz_results.created_at`; attempts without saved answer timestamps are excluded. Missing quizzes or attendance have a count of zero, so a missing record is distinguishable from a recorded zero. An absent exam, an ungraded exam, and invalid marks are excluded rather than counted as zero. All inputs must have dates **before** the exam, and paper/attendance entries created or revised after the exam cannot be used to recreate their historical state. No personal names, email addresses, or teacher remarks are read.

The report waits for at least 30 distinct students and two exam dates; it also needs 30 training students from earlier exam dates and 10 students on the latest date. The latest exam date is the test set. Thresholds are only a guard against reporting a meaningless score with one student: 30 students do not prove a model is reliable. Students can appear in both earlier and later exams, so this measures later performance for a school cohort, not how the model works at a new school. Before using a prediction for decisions, assess error across more terms, schools, and student groups, compare with teacher judgement and the baseline, and check for missing data and unfair disparities.

The app's current Random Forest was trained on 15 illustrative rows in `student_performance.csv` and uses manually entered values. The separate Gradient Boosting scripts use a different dataset and target. Neither validates predictions for this school. Until representative school outcomes are collected and evaluated, teacher actions and student practice suggestions should rely on the observed paper, lab quiz, and attendance evidence.

## Public dataset research: 1,044 subject records

Run the **separate** reproducible experiment from the project root:

```bash
python -m ml.evaluate_uci_research
```

This uses the [UCI Student Performance dataset](https://archive.ics.uci.edu/dataset/320/student%2Bperformance) by Paulo Cortez (2008, DOI: 10.24432/C5TG7T; CC BY 4.0): `student-mat.csv` contains 395 Mathematics subject records and `student-por.csv` contains 649 Portuguese language subject records from two schools in Portugal. Cite the source when presenting these results. The combined 1,044 **subject records are not 1,044 unique students**. The supplied `student-merge.R` matches students using 13 shared attributes. This experiment uses the same attributes to create 662 matching identity *groups*, which are proxies because the released files contain no student IDs and some attribute combinations occur more than once even within a course. A whole group stays in either training or testing, never both.

The experiment predicts final grade `G3` (0–20) using first period grade `G1`, previous failures, study time, absences and subject. It omits the later `G2` grade and all private demographic and family attributes from model inputs. Its 80/20 grouped holdout compares a training-mean baseline, Ridge and Gradient Boosting with fixed settings, reporting overall and per-subject errors in **UCI grade points**. It does not save a model, change app predictions, or evaluate Nepali Grade 10 students. The release does not timestamp study time and absences relative to `G3`, so these results cannot establish prospective early-warning accuracy. A single random holdout is an exploratory result; replicate with grouped validation, check how well any promising model transfers to local school outcomes, and review fairness before use in teaching decisions. The UCI files do not provide per-question topic understanding, so they cannot train the app's topic guidance.
