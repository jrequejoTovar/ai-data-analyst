-- 03_metadata.sql
-- Adds semantic metadata that can later be exposed to the LLM through MCP.

COMMENT ON TABLE public.employees IS 'HR employee analytics dataset used to investigate workforce patterns, employee experience, compensation, performance and attrition.';

COMMENT ON COLUMN public.employees.employee_id IS 'Unique employee identifier.';
COMMENT ON COLUMN public.employees.age IS 'Employee age in years at the snapshot date.';
COMMENT ON COLUMN public.employees.over_18 IS 'Indicates whether the employee is over 18. Observed values: Y.';
COMMENT ON COLUMN public.employees.age_when_hired IS 'Employee age in years when hired.';
COMMENT ON COLUMN public.employees.standard_hours IS 'Standard scheduled working hours.';
COMMENT ON COLUMN public.employees.monthly_rate IS 'Monthly rate associated with the employee record.';
COMMENT ON COLUMN public.employees.daily_rate IS 'Daily rate associated with the employee record.';
COMMENT ON COLUMN public.employees.hourly_rate IS 'Hourly rate associated with the employee record.';
COMMENT ON COLUMN public.employees.fte IS 'Full-time equivalent (FTE) value for the employee.';
COMMENT ON COLUMN public.employees.headcount IS 'Headcount contribution represented by the record.';
COMMENT ON COLUMN public.employees.gender IS 'Employee gender as provided in the source dataset. Observed values: Female, Male.';
COMMENT ON COLUMN public.employees.marital_status IS 'Employee marital status. Observed values: Divorced, Married, Single.';
COMMENT ON COLUMN public.employees.children_num IS 'Number of children recorded for the employee.';
COMMENT ON COLUMN public.employees.education_level IS 'Highest education level category recorded for the employee. Observed values: Bachelor, Below College, College, Doctor, Master.';
COMMENT ON COLUMN public.employees.education_branch IS 'Employee education or study discipline/branch. Observed values: COMPUTER SCIENCE, ELECTRONICS, HR, INFORMATION TECHNOLOGY, MARKETING, SOFTWARE ENGINEERING.';
COMMENT ON COLUMN public.employees.education_grade IS 'Education grade category recorded for the employee. Observed values: DISTINCTION, FIRST CLASS, GOLD MIDDLE, PASS CLASS.';
COMMENT ON COLUMN public.employees.business_unit IS 'Business unit in which the employee works. Observed values: ENG, FIN, HR, IT, PROD DEV, SALES.';
COMMENT ON COLUMN public.employees.job_role IS 'Employee job role. Observed values: A003 Acct Mgr, A004 Sales Mgr, F020 Fin Anly II, H001 Ben Coord, H008 HR Dir, I003 Network Eng, J019 Plant Mngr, J020 Ind Eng I, Z001 Prod Dev I, Z013 RD Mngr.';
COMMENT ON COLUMN public.employees.personal_income_monthly IS 'Employee monthly personal income.';
COMMENT ON COLUMN public.employees.avg_pay_for_similar_exp IS 'Average pay benchmark for employees with similar experience.';
COMMENT ON COLUMN public.employees.distance_from_home IS 'Distance from the employee home to the workplace, in the units used by the source dataset.';
COMMENT ON COLUMN public.employees.total_working_years IS 'Total years of professional working experience.';
COMMENT ON COLUMN public.employees.num_companies_worked IS 'Number of companies the employee has worked for.';
COMMENT ON COLUMN public.employees.tenure_at_company IS 'Number of years the employee has worked at the current company.';
COMMENT ON COLUMN public.employees.years_with_current_manager IS 'Number of years the employee has worked with the current manager.';
COMMENT ON COLUMN public.employees.years_in_current_role IS 'Number of years the employee has been in the current role.';
COMMENT ON COLUMN public.employees.years_since_last_promotion IS 'Number of years since the employee last received a promotion.';
COMMENT ON COLUMN public.employees.training_times_past_year IS 'Number of training sessions completed during the past year.';
COMMENT ON COLUMN public.employees.business_travel IS 'Frequency/category of business travel. Observed values: Non-Travel, Travel_Frequently, Travel_Rarely.';
COMMENT ON COLUMN public.employees.overtime IS 'Indicates whether the employee works overtime. Values in the source include Yes and No.';
COMMENT ON COLUMN public.employees.extra_hours_per_week IS 'Additional hours worked per week beyond the standard schedule.';
COMMENT ON COLUMN public.employees.job_satisfaction IS 'Employee job satisfaction category. Source values include Low, Medium, High and Super High.';
COMMENT ON COLUMN public.employees.job_involvement IS 'Employee job involvement category. Observed values: High, Low, Medium, Super High.';
COMMENT ON COLUMN public.employees.environment_satisfaction IS 'Employee satisfaction with the work environment. Observed values: High, Low, Medium, Super High.';
COMMENT ON COLUMN public.employees.relationship_satisfaction IS 'Employee satisfaction with workplace relationships. Observed values: High, Low, Medium, Super High.';
COMMENT ON COLUMN public.employees.work_life_balance IS 'Employee work-life balance category. Source values include Bad, Good, Better and Best.';
COMMENT ON COLUMN public.employees.year_1_performance IS 'Employee performance category for Year 1. Observed values: EXCELLENT, GOOD, LOW, OUTSTANDING.';
COMMENT ON COLUMN public.employees.year_1_percent_hike IS 'Percentage pay hike associated with Year 1.';
COMMENT ON COLUMN public.employees.year_2_performance IS 'Employee performance category for Year 2. Observed values: EXCELLENT, GOOD, LOW, OUTSTANDING.';
COMMENT ON COLUMN public.employees.year_2_percent_hike IS 'Percentage pay hike associated with Year 2.';
COMMENT ON COLUMN public.employees.attrition IS 'Indicates whether the employee left the organization. Yes means the employee left; No means the employee remained.';
COMMENT ON COLUMN public.employees.snapshot_date IS 'Date on which the employee record snapshot was taken.';
COMMENT ON COLUMN public.employees.hire_date IS 'Date the employee was hired.';
COMMENT ON COLUMN public.employees.termination_date IS 'Date the employee left the organization. Null when no termination date is recorded.';
