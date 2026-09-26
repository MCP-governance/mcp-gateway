-- BoB Corp business database behind the postgres MCP server.
-- Classification lives in registry/catalog.toml, keyed by schema.table:
-- public.* public, sales.orders nonimportant, sales.customers important (PII),
-- hr.employees nonimportant, hr.salaries important.
CREATE SCHEMA IF NOT EXISTS sales;
CREATE SCHEMA IF NOT EXISTS hr;

CREATE TABLE public.products (id int PRIMARY KEY, name text NOT NULL, price int NOT NULL);
INSERT INTO public.products VALUES (1,'BoB Pay Basic',30000),(2,'BoB Pay Pro',150000),(3,'BoB Insight',300000);

CREATE TABLE sales.customers (id text PRIMARY KEY, name text, phone text, rrn text, email text);
INSERT INTO sales.customers VALUES
 ('C-0001','홍길동','010-1234-5678','900101-1234567','hong@example.com'),
 ('C-0002','김영희','010-2345-6789','920202-2345678','younghee@example.com'),
 ('C-0003','이철수','010-3456-7890','880303-1456789','chulsoo@example.com');

CREATE TABLE sales.orders (id serial PRIMARY KEY, customer_id text REFERENCES sales.customers(id),
  product_id int REFERENCES public.products(id), amount int NOT NULL, ordered_at timestamptz NOT NULL);
INSERT INTO sales.orders(customer_id, product_id, amount, ordered_at)
SELECT (ARRAY['C-0001','C-0002','C-0003'])[1 + (g % 3)], 1 + (g % 3), 30000 * (1 + (g % 5)),
       timestamptz '2026-09-01 09:00+09' + (g || ' hours')::interval
FROM generate_series(1, 120) AS g;

CREATE TABLE hr.employees (emp_no text PRIMARY KEY, name text, department text, title text, hired_at date);
INSERT INTO hr.employees VALUES
 ('EMP-101','박소은','보안기술팀','사원','2025-03-02'), ('EMP-102','김미소','보안기술팀','사원','2025-03-02'),
 ('EMP-103','양승권','플랫폼개발팀','사원','2025-03-02'), ('EMP-104','정원재','데이터분석팀','사원','2025-03-02');

CREATE TABLE hr.salaries (emp_no text PRIMARY KEY REFERENCES hr.employees(emp_no), base_salary int, bonus int);
INSERT INTO hr.salaries VALUES ('EMP-101',52000000,4000000),('EMP-102',51000000,3500000),
 ('EMP-103',54000000,4200000),('EMP-104',53000000,3900000);
