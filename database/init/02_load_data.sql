-- 02_load_data.sql
-- Loads the source Excel data after conversion to CSV.

\copy public.employees (employee_id, age, over_18, age_when_hired, standard_hours, monthly_rate, daily_rate, hourly_rate, fte, headcount, gender, marital_status, children_num, education_level, education_branch, education_grade, business_unit, job_role, personal_income_monthly, avg_pay_for_similar_exp, distance_from_home, total_working_years, num_companies_worked, tenure_at_company, years_with_current_manager, years_in_current_role, years_since_last_promotion, training_times_past_year, business_travel, overtime, extra_hours_per_week, job_satisfaction, job_involvement, environment_satisfaction, relationship_satisfaction, work_life_balance, year_1_performance, year_1_percent_hike, year_2_performance, year_2_percent_hike, attrition, snapshot_date, hire_date, termination_date) FROM '/data/employees.csv' WITH (FORMAT csv, HEADER true, DELIMITER ';', NULL '', ENCODING 'UTF8');

ANALYZE public.employees;
