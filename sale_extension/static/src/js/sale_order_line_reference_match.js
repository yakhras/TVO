/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { onMounted } from "@odoo/owl";
import { SaleOrderLineProductField } from "@sale/js/sale_product_field";

patch(SaleOrderLineProductField.prototype, {
    setup() {
        super.setup();
        // The product field uses a customized Many2XAutocomplete (from
        // account's ProductLabelSectionAndNoteField) whose own input ref
        // doesn't line up with the generic AutoComplete.selectOption's
        // `params.input`, so that can't be relied on here. Instead, track
        // the raw typed text directly off the field's own input element,
        // which `autocompleteContainerRef` (set up by core Many2OneField)
        // reliably points at regardless of which autocomplete subclass is
        // rendered.
        onMounted(() => {
            const inputEl = this.autocompleteContainerRef.el?.querySelector("input");
            if (inputEl) {
                inputEl.addEventListener("input", (ev) => {
                    this._lastTypedReference = ev.target.value?.trim();
                });
            }
        });
    },

    async _onProductTemplateUpdate() {
        const reference = this._lastTypedReference;
        this._lastTypedReference = undefined;
        if (reference) {
            const result = await this.orm.call(
                "product.template",
                "get_variant_by_reference",
                [this.props.record.data.product_template_id[0], reference],
                { context: this.context },
            );
            if (result && result.product_id) {
                await this.props.record.update({
                    product_id: [result.product_id, result.product_name],
                });
                this._onProductUpdate();
                return;
            }
        }
        await super._onProductTemplateUpdate();
    },
});
