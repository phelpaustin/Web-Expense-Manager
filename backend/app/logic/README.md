# Ported logic modules

Copy reusable, Streamlit-free modules from the old project into this folder,
one feature at a time. Good candidates:

- analytics.py, analytics_advanced.py
- budget_manager.py, financial_metrics.py
- ml_categorizer.py, recurring_manager.py, income_manager.py
- currency_manager.py, spending_intelligence.py, tax_export.py
- models.py, validators.py, date_utils.py, receipt_ocr.py

Do NOT copy Streamlit-bound files (views/, ui_components.py, theme.py,
page_helpers.py, Main_Dashboard_App.py) or secrets/data files.
