-- =============================================================================
-- Script Name : 05_system_parameters_seed.sql
-- Purpose     : Seed data for the gateway adapter registry and runtime
--               system parameters.
-- Author      : Harish
-- Run Order   : AFTER 04_create_enterprise_tables.sql
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Gateway adapters — today only MOCK_BANK is enabled. Adding a real
-- provider later is a new row here plus a new adapter class in
-- app/services/payment/adapters/ — the orchestrator and business services
-- do not change.
-- -----------------------------------------------------------------------------
INSERT INTO payment_gateway_config (gateway_code, gateway_name, adapter_class, is_enabled, config_json)
VALUES (
    'MOCK_BANK',
    'Offline Mock Bank Simulator',
    'app.services.payment.adapters.mock_bank_adapter.MockBankAdapter',
    1,
    '{"base_url": "http://127.0.0.1:8000", "supports_modes": ["UPI_QR", "UPI_ID", "NET_BANKING"]}'
);

INSERT INTO payment_gateway_config (gateway_code, gateway_name, adapter_class, is_enabled, config_json)
VALUES (
    'RAZORPAY',
    'Razorpay (not yet wired — placeholder row)',
    'app.services.payment.adapters.razorpay_adapter.RazorpayAdapter',
    0,
    '{"note": "Disabled placeholder — enable and configure when a real Razorpay integration is built"}'
);

INSERT INTO payment_gateway_config (gateway_code, gateway_name, adapter_class, is_enabled, config_json)
VALUES (
    'PHONEPE',
    'PhonePe (not yet wired — placeholder row)',
    'app.services.payment.adapters.phonepe_adapter.PhonePeAdapter',
    0,
    '{"note": "Disabled placeholder — enable and configure when a real PhonePe integration is built"}'
);

-- -----------------------------------------------------------------------------
-- Runtime system parameters
-- -----------------------------------------------------------------------------
INSERT INTO system_parameters (param_key, param_value, description, is_editable)
VALUES ('QR_PAYLOAD_TTL_SECONDS', '900', 'Seconds before a generated UPI QR payload expires', 1);

INSERT INTO system_parameters (param_key, param_value, description, is_editable)
VALUES ('RECEIPT_FOOTER_TEXT', 'This is a system-generated receipt and does not require a physical signature.', 'Footer text printed on PDF receipts', 1);

INSERT INTO system_parameters (param_key, param_value, description, is_editable)
VALUES ('MERCHANT_DISPLAY_NAME', 'Demo University', 'Institute name shown on receipts and QR branding', 1);

INSERT INTO system_parameters (param_key, param_value, description, is_editable)
VALUES ('MAX_WEBHOOK_RETRY_ATTEMPTS', '3', 'Max attempts the mock bank simulator will retry a webhook delivery', 1);

INSERT INTO system_parameters (param_key, param_value, description, is_editable)
VALUES ('SCHEMA_VERSION', '2.0.0', 'Current enterprise schema version (tracks 03/04/05 migrations applied)', 0);

COMMIT;
