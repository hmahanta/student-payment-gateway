-- =============================================================================
-- Script Name : 02_seed_sample_data.sql
-- Purpose     : Sample data for local offline testing of the Payment Aggregator
-- Author      : Harish
-- =============================================================================

INSERT INTO students (student_id, student_name, email, phone_number, assigned_virtual_account, assigned_ifsc, assigned_upi_id)
VALUES ('STU1001', 'Aditi Sharma', 'aditi.sharma@example.com', '9876543210', 'VA00000001001', 'MOCK0001234', 'stu1001@mockbank');

INSERT INTO students (student_id, student_name, email, phone_number, assigned_virtual_account, assigned_ifsc, assigned_upi_id)
VALUES ('STU1002', 'Rahul Verma', 'rahul.verma@example.com', '9876543211', 'VA00000001002', 'MOCK0001234', 'stu1002@mockbank');

INSERT INTO students (student_id, student_name, email, phone_number, assigned_virtual_account, assigned_ifsc, assigned_upi_id)
VALUES ('STU1003', 'Meera Iyer', 'meera.iyer@example.com', '9876543212', 'VA00000001003', 'MOCK0001234', 'stu1003@mockbank');

INSERT INTO fee_invoices (invoice_id, student_id, fee_description, academic_term, amount_due, amount_paid, invoice_status, due_date)
VALUES ('INV2001', 'STU1001', 'Semester 5 Tuition Fee', '2026-ODD', 45000.00, 0, 'PENDING', DATE '2026-07-31');

INSERT INTO fee_invoices (invoice_id, student_id, fee_description, academic_term, amount_due, amount_paid, invoice_status, due_date)
VALUES ('INV2002', 'STU1002', 'Semester 5 Tuition Fee', '2026-ODD', 45000.00, 0, 'PENDING', DATE '2026-07-31');

INSERT INTO fee_invoices (invoice_id, student_id, fee_description, academic_term, amount_due, amount_paid, invoice_status, due_date)
VALUES ('INV2003', 'STU1003', 'Hostel Fee', '2026-ODD', 22000.00, 22000.00, 'PAID', DATE '2026-06-30');

COMMIT;
