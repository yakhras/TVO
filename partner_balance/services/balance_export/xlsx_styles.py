# -*- coding: utf-8 -*-
"""Centralized style definitions for Excel export."""


class ExportStyles:
    """Manages all Excel formatting styles for balance exports."""
    

    # Color palette
    COLORS = {
        'primary_dark': '#1e3a8a',
        'primary_light': '#3b82f6',
        'header_bg': '#475569',
        'section_bg': '#374151',
        'row_alt': '#f8f9fa',
        'success': '#059669',
        'success_bg': '#f0fdf4',
        'success_light': '#ecfdf5',
        'danger': '#dc2626',
        'info_bg': '#dbeafe',
        'neutral_bg': '#f3f4f6',
        'title_bg': '#f1f5f9',
        'title_text': '#1e40af',
        'border': '#e2e8f0',
        'white': 'white',
    }

    def __init__(self, workbook, monetary_format='#,##0.00', direction='ltr'):
        self.workbook = workbook
        self.monetary_format = monetary_format
        self.float_format = '#,##0.00'
        self.rtl = direction == 'rtl'
        self._init_styles()

    def _align(self, base):
        """Mirror a horizontal alignment when the report direction is RTL."""
        if not self.rtl:
            return base
        return {'left': 'right', 'right': 'left'}.get(base, base)

    def _init_styles(self):
        """Initialize all style formats."""
        self._init_base_styles()
        self._init_header_styles()
        self._init_data_styles()
        self._init_summary_styles()

    def _init_base_styles(self):
        """Base styles used across the report."""
        self.base = self.workbook.add_format({
            'text_wrap': True,
            'font_size': 8,
            'align': self._align('left'),
            'valign': 'vcenter',
            'border': 1,
        })

        self.bold = self.workbook.add_format({
            'bold': True,
        })

        self.bold_bg = self.workbook.add_format({
            'text_wrap': True,
            'bold': True,
            'bg_color': '#e9ecef',
        })

    def _init_header_styles(self):
        """Styles for headers and titles."""
        self.company_header = self.workbook.add_format({
            'bold': True,
            'font_size': 12,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': self.COLORS['primary_dark'],
            'font_color': self.COLORS['white'],
            'border': 1,
            'border_color': self.COLORS['primary_light'],
        })

        self.report_title = self.workbook.add_format({
            'bold': True,
            'font_size': 12,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': self.COLORS['title_bg'],
            'font_color': self.COLORS['title_text'],
            'border': 1,
            'border_color': self.COLORS['border'],
        })

        self.section_header = self.workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': self.COLORS['section_bg'],
            'font_color': self.COLORS['white'],
            'border': 1,
        })

        self.transaction_header = self.workbook.add_format({
            'text_wrap': True,
            'bold': True,
            'align': 'left',
            'valign': 'vcenter',
            'bg_color': self.COLORS['header_bg'],
            'font_color': self.COLORS['white'],
            'border': 1,
            'font_size': 10,
        })

    def _init_data_styles(self):
        """Styles for data rows."""
        self.date = self.workbook.add_format({
            'text_wrap': True,
            'num_format': 'yyyy-mm-dd',
            'font_size': 8,
            'align': self._align('left'),
            'valign': 'vcenter',
            'border': 1,
        })

        self.datetime = self.workbook.add_format({
            'text_wrap': True,
            'num_format': 'yyyy-mm-dd hh:mm:ss',
            'font_size': 8,
            'align': self._align('left'),
            'valign': 'vcenter',
            'border': 1,
        })

        self._float_style = self.workbook.add_format({
            'text_wrap': True,
            'font_size': 8,
            'align': self._align('left'),
            'valign': 'vcenter',
            'border': 1,
            'num_format': self.float_format,
        })

        self.opening_balance = self.workbook.add_format({
            'num_format': self.monetary_format,
            'align': self._align('left'),
            'valign': 'vcenter',
            'text_wrap': True,
            'bold': True,
            'bg_color': self.COLORS['info_bg'],
            'border': 1,
            'font_size': 8,
        })

        self.partner_name = self.workbook.add_format({
            'align': self._align('left'),
            'valign': 'vcenter',
            'text_wrap': True,
            'bold': True,
            'bg_color': self.COLORS['neutral_bg'],
            'border': 1,
            'font_size': 11,
        })

        self.product_header = self.workbook.add_format({
            'bold': True,
            'font_size': 8,
            'bg_color': '#e0f2fe',
            'border': 1,
            'align': self._align('left'),
            'valign': 'vcenter',
            'text_wrap': True,
        })

        self.product_cell = self.workbook.add_format({
            'font_size': 7,
            'bg_color': '#f0f9ff',
            'border': 1,
            'align': self._align('left'),
            'valign': 'vcenter',
            'text_wrap': True,
        })

        self.product_cell_number = self.workbook.add_format({
            'font_size': 7,
            'bg_color': '#f0f9ff',
            'border': 1,
            'align': 'right',
            'valign': 'vcenter',
            'num_format': '#,##0.00',
        })

    def _init_summary_styles(self):
        """Styles for summary and totals."""
        self.summary_metric = self.workbook.add_format({
            'align': 'left',
            'valign': 'vcenter',
            'text_wrap': True,
            'font_size': 10,
            'bold': True,
            'bg_color': self.COLORS['success_light'],
            'border': 1,
        })

        self.summary_value = self.workbook.add_format({
            'num_format': self.monetary_format,
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'font_color': self.COLORS['success'],
            'bg_color': self.COLORS['success_bg'],
            'border': 1,
        })

        self.negative_value = self.workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'bold': True,
            'font_color': self.COLORS['danger'],
            'border': 1,
            'num_format': self.monetary_format,
        })

        self.monetary = self.workbook.add_format({
            'bold': True,
            'bg_color': '#4F81BD',
            'font_size': 8,
            'font_color': self.COLORS['white'],
            'border': 1,
            'align': 'center',
            'num_format': self.monetary_format,
        })

        self.metadata = self.workbook.add_format({
            'bg_color': self.COLORS['row_alt'],
            'border': 1,
        })

    def get_cell_style(self, value, column_type=None):
        """Get appropriate style based on value type and column."""
        import datetime

        if column_type == 'monetary':
            return self.monetary
        elif column_type == 'date':
            return self.date
        elif column_type == 'datetime':
            return self.datetime

        if isinstance(value, datetime.datetime):
            return self.datetime
        elif isinstance(value, datetime.date):
            return self.date
        elif isinstance(value, float):
            return self._float_style

        return self.base
