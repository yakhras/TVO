/** @odoo-module **/

import { registry } from "@web/core/registry";
import { x2ManyCommands } from "@web/core/orm_service";
import { serializeDateTime } from "@web/core/l10n/dates";
import { getSelectedCustomPtav } from "@sale/js/sale_utils";
import { SaleOrderLineProductField, saleOrderLineProductField } from "@sale/js/sale_product_field";
import { ProductConfiguratorDialog } from "@sale/js/product_configurator_dialog/product_configurator_dialog";

const { DateTime } = luxon;

async function applyProduct(record, product) {
    const customAttributesCommands = [x2ManyCommands.set([])];
    for (const ptal of product.attribute_lines) {
        const selectedCustomPTAV = getSelectedCustomPtav(ptal);
        if (selectedCustomPTAV) {
            customAttributesCommands.push(
                x2ManyCommands.create(undefined, {
                    custom_product_template_attribute_value_id: [selectedCustomPTAV.id, ""],
                    custom_value: ptal.customValue,
                })
            );
        }
    }
    const noVariantPTAVIds = product.attribute_lines
        .filter(ptal => ptal.create_variant === "no_variant")
        .flatMap(ptal => ptal.selected_attribute_value_ids);

    await record._update({
        product_id: [product.id, product.display_name],
        product_qty: product.quantity,
        product_no_variant_attribute_value_ids: [x2ManyCommands.set(noVariantPTAVIds)],
        product_custom_attribute_value_ids: customAttributesCommands,
    });
}

export class PurchaseRequisitionLineProductField extends SaleOrderLineProductField {
    async _openProductConfigurator(edit = false) {
        const prRecord = this.props.record.model.root;
        const prLine = this.props.record.data;

        let ptavIds = this._getVariantPtavIds(prLine);
        let customPtavs = [];
        if (edit) {
            ptavIds.push(...this._getNoVariantPtavIds(prLine));
            customPtavs = await this._getCustomPtavs(prLine);
        }

        this.dialog.add(ProductConfiguratorDialog, {
            productTemplateId: prLine.product_template_id[0],
            ptavIds: ptavIds,
            customPtavs: customPtavs,
            quantity: prLine.product_qty || 1,
            productUOMId: prLine.product_uom_id ? prLine.product_uom_id[0] : false,
            companyId: prRecord.data.company_id ? prRecord.data.company_id[0] : false,
            pricelistId: false,
            currencyId: prRecord.data.currency_id ? prRecord.data.currency_id[0] : false,
            soDate: serializeDateTime(DateTime.now()),
            edit: edit,
            save: async (mainProduct, optionalProducts) => {
                await Promise.all([
                    applyProduct(this.props.record, mainProduct),
                    ...optionalProducts.map(async product => {
                        const line = await prRecord.data.line_ids.addNewRecord({
                            position: 'bottom', mode: 'readonly',
                        });
                        await applyProduct(line, product);
                    }),
                ]);
                prRecord.data.line_ids.leaveEditMode();
            },
            discard: () => {
                if (!edit) {
                    prRecord.data.line_ids.delete(this.props.record);
                }
            },
        });
    }
}

export const purchaseRequisitionLineProductConfiguratorField = {
    ...saleOrderLineProductField,
    component: PurchaseRequisitionLineProductField,
};

registry.category("fields").add("purchase_requisition_line_product_configurator", purchaseRequisitionLineProductConfiguratorField);
