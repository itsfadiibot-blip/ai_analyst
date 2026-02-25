# Data Quality Report
**Generated:** 2026-02-25 05:29

## account_move
**Sampled rows:** 31,776

### Null/Empty Field Percentages
| Field | Null % |
|-------|--------|
| message_main_attachment_id | 100.0% ⚠️ |
| access_token | 100.0% ⚠️ |
| tax_cash_basis_rec_id | 100.0% ⚠️ |
| tax_cash_basis_origin_move_id | 100.0% ⚠️ |
| reversed_entry_id | 100.0% ⚠️ |
| invoice_payment_term_id | 100.0% ⚠️ |
| qr_code_method | 100.0% ⚠️ |
| invoice_source_email | 100.0% ⚠️ |
| invoice_cash_rounding_id | 100.0% ⚠️ |
| secure_sequence_number | 100.0% ⚠️ |
| inalterable_hash | 100.0% ⚠️ |
| edi_state | 100.0% ⚠️ |
| extract_document_uuid | 100.0% ⚠️ |
| campaign_id | 100.0% ⚠️ |
| source_id | 100.0% ⚠️ |
| medium_id | 100.0% ⚠️ |
| payment_state_before_switch | 100.0% ⚠️ |
| transfer_model_id | 100.0% ⚠️ |
| tax_closing_end_date | 100.0% ⚠️ |
| tax_report_control_error | 100.0% ⚠️ |

## account_move_line
**Sampled rows:** 36,539
⚠️ **Duplicate names:** 6,392

### Null/Empty Field Percentages
| Field | Null % |
|-------|--------|
| reconcile_model_id | 100.0% ⚠️ |
| group_tax_id | 100.0% ⚠️ |
| expected_pay_date | 100.0% ⚠️ |
| next_action_date | 100.0% ⚠️ |
| followup_line_id | 100.0% ⚠️ |
| last_followup_date | 100.0% ⚠️ |
| purchase_line_id | 100.0% ⚠️ |
| is_landed_costs_line | 100.0% ⚠️ |
| deferred_start_date | 100.0% ⚠️ |
| deferred_end_date | 100.0% ⚠️ |
| analytic_distribution | 100.0% ⚠️ |
| discount_date | 100.0% ⚠️ |
| subscription_id | 100.0% ⚠️ |
| cogs_origin_id | 100.0% ⚠️ |
| vehicle_id | 100.0% ⚠️ |
| statement_line_id | 99.7% ⚠️ |
| statement_id | 99.7% ⚠️ |
| tax_line_id | 99.7% ⚠️ |
| tax_group_id | 99.7% ⚠️ |
| tax_base_amount | 99.7% ⚠️ |

## pos_order
**Sampled rows:** 1,730
⚠️ **Duplicate names:** 7

### Null/Empty Field Percentages
| Field | Null % |
|-------|--------|
| procurement_group_id | 100.0% ⚠️ |
| fiscal_position_id | 100.0% ⚠️ |
| shipping_date | 100.0% ⚠️ |
| next_online_payment_amount | 100.0% ⚠️ |
| is_gift_card | 100.0% ⚠️ |
| account_move | 99.8% ⚠️ |
| crm_team_id | 95.0% ⚠️ |
| access_token | 77.6%  |
| last_order_preparation_change | 77.6%  |
| ticket_code | 77.6%  |
| note | 77.2%  |
| employee_id | 59.1%  |
| pricelist_id | 22.4%  |
| partner_id | 3.2%  |
| to_invoice | 0.1%  |

## pos_order_line
**Sampled rows:** 2,638
⚠️ **Duplicate names:** 2

### Null/Empty Field Percentages
| Field | Null % |
|-------|--------|
| notice | 100.0% ⚠️ |
| sale_order_origin_id | 100.0% ⚠️ |
| sale_order_line_id | 100.0% ⚠️ |
| down_payment_details | 100.0% ⚠️ |
| combo_parent_id | 100.0% ⚠️ |
| reward_id | 100.0% ⚠️ |
| coupon_id | 100.0% ⚠️ |
| reward_identifier_code | 100.0% ⚠️ |
| is_reward_line | 100.0% ⚠️ |
| points_cost | 100.0% ⚠️ |
| refunded_orderline_id | 94.0% ⚠️ |
| customer_note | 82.8% ⚠️ |
| price_extra | 77.7%  |
| uuid | 77.7%  |
| skip_change | 77.7%  |
| total_cost | 0.5%  |

## product_attribute
**Sampled rows:** 5

### Null/Empty Field Percentages
| Field | Null % |
|-------|--------|
| sequence | 60.0%  |

## product_attribute_value
**Sampled rows:** 321

### Null/Empty Field Percentages
| Field | Null % |
|-------|--------|
| html_color | 100.0% ⚠️ |
| default_extra_price | 97.8% ⚠️ |
| sequence | 85.4% ⚠️ |
| is_custom | 85.4% ⚠️ |

## product_category
**Sampled rows:** 10
⚠️ **Duplicate names:** 1

### Null/Empty Field Percentages
| Field | Null % |
|-------|--------|
| removal_strategy_id | 100.0% ⚠️ |
| product_properties_definition | 100.0% ⚠️ |
| parent_id | 40.0%  |

## product_product
**Sampled rows:** 200,000

### Null/Empty Field Percentages
| Field | Null % |
|-------|--------|
| volume | 100.0% ⚠️ |
| base_unit_id | 100.0% ⚠️ |
| x_studio_list_price | 100.0% ⚠️ |
| name | 100.0% ⚠️ |
| has_lifestyle | 100.0% ⚠️ |
| available_in_pos | 100.0% ⚠️ |
| "timestamp" | 100.0% ⚠️ |
| available_to_sell_qty | 100.0% ⚠️ |
| ordered_qty | 100.0% ⚠️ |
| qty_purchased | 100.0% ⚠️ |
| returned_qty | 100.0% ⚠️ |
| delivered_qty | 100.0% ⚠️ |
| actual_sold | 100.0% ⚠️ |
| in_process | 100.0% ⚠️ |
| mayoral_bought | 100.0% ⚠️ |
| mayoral_sold | 100.0% ⚠️ |
| mayoral_inprocess | 100.0% ⚠️ |
| jc_mirdif_sold | 100.0% ⚠️ |
| lot_properties_definition | 100.0% ⚠️ |
| ribbon_id | 100.0% ⚠️ |

## product_template
**Sampled rows:** 54,867
⚠️ **Duplicate names:** 14,395

### Null/Empty Field Percentages
| Field | Null % |
|-------|--------|
| description_purchase | 100.0% ⚠️ |
| company_id | 100.0% ⚠️ |
| sale_line_warn_msg | 100.0% ⚠️ |
| description_picking | 100.0% ⚠️ |
| description_pickingout | 100.0% ⚠️ |
| description_pickingin | 100.0% ⚠️ |
| purchase_line_warn_msg | 100.0% ⚠️ |
| hs_code | 100.0% ⚠️ |
| website_id | 100.0% ⚠️ |
| website_meta_og_img | 100.0% ⚠️ |
| website_description | 100.0% ⚠️ |
| website_ribbon_id | 100.0% ⚠️ |
| base_unit_id | 100.0% ⚠️ |
| x_testprodate | 100.0% ⚠️ |
| x_sale | 100.0% ⚠️ |
| sash | 100.0% ⚠️ |
| sfcc_image_url | 100.0% ⚠️ |
| x_sfcc_primary_category | 100.0% ⚠️ |
| split_method_landed_cost | 100.0% ⚠️ |
| email_template_id | 100.0% ⚠️ |

## res_country
**Sampled rows:** 250

### Null/Empty Field Percentages
| Field | Null % |
|-------|--------|
| address_view_id | 100.0% ⚠️ |
| vat_label | 83.2% ⚠️ |

## res_partner
**Sampled rows:** 120,000
⚠️ **Duplicate names:** 67,104

### Null/Empty Field Percentages
| Field | Null % |
|-------|--------|
| date | 100.0% ⚠️ |
| title | 100.0% ⚠️ |
| ref | 100.0% ⚠️ |
| user_id | 100.0% ⚠️ |
| vat | 100.0% ⚠️ |
| website | 100.0% ⚠️ |
| employee | 100.0% ⚠️ |
| function | 100.0% ⚠️ |
| industry_id | 100.0% ⚠️ |
| company_name | 100.0% ⚠️ |
| signup_token | 100.0% ⚠️ |
| signup_type | 100.0% ⚠️ |
| signup_expiration | 100.0% ⚠️ |
| team_id | 100.0% ⚠️ |
| ocn_token | 100.0% ⚠️ |
| additional_info | 100.0% ⚠️ |
| last_time_entries_checked | 100.0% ⚠️ |
| invoice_warn_msg | 100.0% ⚠️ |
| sale_warn_msg | 100.0% ⚠️ |
| picking_warn_msg | 100.0% ⚠️ |

## sale_order
**Sampled rows:** 14,375
⚠️ **Duplicate names:** 1

### Null/Empty Field Percentages
| Field | Null % |
|-------|--------|
| campaign_id | 100.0% ⚠️ |
| source_id | 100.0% ⚠️ |
| medium_id | 100.0% ⚠️ |
| origin | 100.0% ⚠️ |
| client_order_ref | 100.0% ⚠️ |
| reference | 100.0% ⚠️ |
| validity_date | 100.0% ⚠️ |
| analytic_account_id | 100.0% ⚠️ |
| payment_term_id | 100.0% ⚠️ |
| signed_by | 100.0% ⚠️ |
| signed_on | 100.0% ⚠️ |
| commitment_date | 100.0% ⚠️ |
| sale_order_template_id | 100.0% ⚠️ |
| incoterm | 100.0% ⚠️ |
| delivery_message | 100.0% ⚠️ |
| delivery_rating_success | 100.0% ⚠️ |
| website_id | 100.0% ⚠️ |
| shop_warning | 100.0% ⚠️ |
| "supProductImageURL" | 100.0% ⚠️ |
| "supProductLink" | 100.0% ⚠️ |

## sale_order_line
**Sampled rows:** 15,968
⚠️ **Duplicate names:** 9,866

### Null/Empty Field Percentages
| Field | Null % |
|-------|--------|
| display_type | 100.0% ⚠️ |
| product_packaging_id | 100.0% ⚠️ |
| route_id | 100.0% ⚠️ |
| linked_line_id | 100.0% ⚠️ |
| shop_warning | 100.0% ⚠️ |
| analytic_distribution | 100.0% ⚠️ |
| parent_line_id | 100.0% ⚠️ |
| project_id | 100.0% ⚠️ |
| task_id | 100.0% ⚠️ |
| product | 100.0% ⚠️ |
| code | 100.0% ⚠️ |
| message | 100.0% ⚠️ |
| description | 100.0% ⚠️ |
| reward_id | 100.0% ⚠️ |
| coupon_id | 100.0% ⚠️ |
| reward_identifier_code | 100.0% ⚠️ |
| points_cost | 100.0% ⚠️ |
| interwarehouse_channel_id | 100.0% ⚠️ |
| is_expense | 99.9% ⚠️ |
| is_downpayment | 99.8% ⚠️ |

## stock_location
**Sampled rows:** 5,000
⚠️ **Duplicate names:** 2,472

### Null/Empty Field Percentages
| Field | Null % |
|-------|--------|
| removal_strategy_id | 100.0% ⚠️ |
| next_inventory_date | 100.0% ⚠️ |
| storage_category_id | 100.0% ⚠️ |
| valuation_in_account_id | 100.0% ⚠️ |
| valuation_out_account_id | 100.0% ⚠️ |
| return_location | 99.9% ⚠️ |
| location_type | 99.9% ⚠️ |
| iwt_qty | 99.9% ⚠️ |
| comment | 99.7% ⚠️ |
| last_inventory_date | 95.4% ⚠️ |
| x_studio_sequence | 48.5%  |
| barcode | 48.4%  |
| warehouse_id | 10.6%  |
| location_id | 10.4%  |
| company_id | 0.1%  |
| replenish_location | 0.1%  |

## stock_move
**Sampled rows:** 24,914
⚠️ **Duplicate names:** 9,073

### Null/Empty Field Percentages
| Field | Null % |
|-------|--------|
| delay_alert_date | 100.0% ⚠️ |
| restrict_partner_id | 100.0% ⚠️ |
| package_level_id | 100.0% ⚠️ |
| next_serial | 100.0% ⚠️ |
| orderpoint_id | 100.0% ⚠️ |
| product_packaging_id | 100.0% ⚠️ |
| scrap_id | 100.0% ⚠️ |
| origin_returned_move_id | 98.1% ⚠️ |
| to_refund | 97.7% ⚠️ |
| next_serial_count | 97.6% ⚠️ |
| move_reason | 96.9% ⚠️ |
| purchase_line_id | 93.2% ⚠️ |
| price_unit | 91.8% ⚠️ |
| is_inventory | 77.9%  |
| sale_line_id | 77.6%  |
| rule_id | 68.2%  |
| partner_id | 65.2%  |
| warehouse_id | 59.9%  |
| date_deadline | 59.4%  |
| origin | 58.5%  |

## stock_quant
**Sampled rows:** 100,000

### Null/Empty Field Percentages
| Field | Null % |
|-------|--------|
| lot_id | 100.0% ⚠️ |
| package_id | 100.0% ⚠️ |
| owner_id | 100.0% ⚠️ |
| user_id | 100.0% ⚠️ |
| accounting_date | 100.0% ⚠️ |
| pos_order_no | 100.0% ⚠️ |
| working_quant | 100.0% ⚠️ |
| storage_category_id | 100.0% ⚠️ |
| inventory_quantity | 99.9% ⚠️ |
| inventory_date | 99.3% ⚠️ |
| reason | 99.0% ⚠️ |
| company_id | 45.6%  |
| write_uid | 0.7%  |
| create_uid | 0.5%  |
