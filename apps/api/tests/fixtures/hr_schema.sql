-- Fixture database exercising the hard cases from the design spec:
-- an undeclared relationship, cryptic legacy names, Persian data, coded status columns.

CREATE TABLE departments (
    id serial PRIMARY KEY,
    name text NOT NULL
);
COMMENT ON TABLE departments IS 'واحدهای سازمانی';

CREATE TABLE employees (
    id serial PRIMARY KEY,
    full_name text NOT NULL,
    national_id char(10),
    mobile varchar(11),
    dept_id integer NOT NULL REFERENCES departments(id),
    salary bigint,
    hired_on date
);

-- No declared foreign key: emp_id must be discovered by the join probe.
CREATE TABLE leave_requests (
    id serial PRIMARY KEY,
    emp_id integer NOT NULL,
    status smallint NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL
);
COMMENT ON COLUMN leave_requests.status IS '1=در انتظار 2=تایید شده 3=رد شده';

-- Cryptic legacy table: the case that motivates value sampling.
CREATE TABLE t_mst_01 (
    fld_001 serial PRIMARY KEY,
    fld_002 integer NOT NULL,
    fld_003 varchar(11)
);

CREATE VIEW v_active_employees AS
    SELECT id, full_name, dept_id FROM employees WHERE hired_on IS NOT NULL;

INSERT INTO departments (name) VALUES ('مالی'), ('فناوری اطلاعات'), ('منابع انسانی');
INSERT INTO employees (full_name, national_id, mobile, dept_id, salary, hired_on) VALUES
    ('علی رضایی', '0079542619', '09121234567', 1, 120000000, '2020-03-01'),
    ('مریم کریمی', '0084575941', '09354445566', 2, 180000000, '2021-06-15'),
    ('حسن محمدی', '0068518123', '09127778899', 2, 150000000, '2019-01-20');
INSERT INTO leave_requests (emp_id, status, start_date, end_date) VALUES
    (1, 2, '2026-07-01', '2026-07-05'),
    (2, 1, '2026-07-10', '2026-07-12'),
    (3, 3, '2026-07-15', '2026-07-16'),
    (1, 2, '2026-07-20', '2026-07-21');
INSERT INTO t_mst_01 (fld_002, fld_003) VALUES
    (1, '09121234567'), (2, '09354445566'), (3, '09127778899');

ANALYZE;
