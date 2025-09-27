# Web App for College Applications
(VT Hackathon 13)
Centralized Platform for College Applications

## Code Stack
    - React (Maybe Javascript)
    - HTML/CSS
    - Potentially using Gemini?
    - SQL database for storing user information
    - Definitely need to use Databricks

## Welcome Page
    - Animation in the background
    - Sign-in with email and password
    - Smaller block beneath sign-in for create user account
        - Ask name, school, year, GPA beneath year, email, password, intended major (option for "I don't know yet.")
        - Optional profile picture upload
        - Sign-in for Canvas API to get grades, assignments, etc.
            - Option to skip Canvas sign-in for no grade integration
            - Compile grades with animated loading screen (building your profile, checking grades, etc)
        - "Is all this information correct?"
        - "Let's talk colleges. Based on your grades and choice of major, here are good fits for you."
            - Top 10 Majors from some source
            - Top 50, Top 100, option to search colleges
        - Go to dashboard with a big "Welcome, {NAME}" the first time a user enters the dashboard

## Dashboard
    - Left side has a vertical bar menu with dashboard (highlighted because on current page), account, settings, log out, each of the boxes
    - Top right has profile picture to click on to get to account, log out
    - Right side bar menu below profile picture with percentile for particular colleges either fit or selected
        - Reach, target, then safety schools descending
    - Four boxes in different parts of the screen each in a quadrant but not bordering, each box has bulletin format, be able to click into a full window mode of the box
        - Planning what grades to achieve better stats in college application success
        - Insights box using Gemini API including total GPA (unweighted and weighted), extracurriculars
            - Full window mode contains percentiles for target schools, different schools to target, ranking, potential success score, number of applications, box for each school
            - Box for a few ideal schools with average school GPA, percentiles of student, 
        - Essays box with brief analysis of most recent essay, "let's finish these incomplete essays"
        - Scholarships box with recommended scholarships for student, recommended major, grades, etc (maybe using ScholarshipOwl REST API)
        - To-do list/calendar configurable by user for adding essay due dates/scholar deadlines/and more
    - Bar across top saying "Good morning, afternoon, or evening, {NAME}" which has a typed animation when showing it each time you log on
