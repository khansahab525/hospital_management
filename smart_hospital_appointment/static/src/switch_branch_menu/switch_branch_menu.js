/** @odoo-module **/

import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

import { Component } from "@odoo/owl";

export class SwitchBranchMenu extends Component {
    static template = "smart_hospital_appointment.SwitchBranchMenu";
    static components = { Dropdown, DropdownItem };
    static props = {};

    setup() {
        this.branchService = useService("hospital_branch");
    }

    get branches() {
        return Object.values(this.branchService.allowedBranches).sort((a, b) =>
            a.name.localeCompare(b.name)
        );
    }

    get currentBranchName() {
        return this.branchService.currentBranch?.name || "";
    }

    isCurrent(branchId) {
        return Number(branchId) === Number(this.branchService.currentBranchId);
    }

    async switchToBranch(branchId) {
        if (!this.isCurrent(branchId)) {
            await this.branchService.setBranch(branchId);
        }
    }
}

export const systrayItem = {
    Component: SwitchBranchMenu,
    isDisplayed(env) {
        return env.services.hospital_branch && Object.keys(env.services.hospital_branch.allowedBranches).length > 0;
    },
};

registry.category("systray").add("SwitchBranchMenu", systrayItem, { sequence: 2 });
