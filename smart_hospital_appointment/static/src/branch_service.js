/** @odoo-module **/

import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { session } from "@web/session";

export const branchService = {
    dependencies: ["user", "rpc"],
    start(env, { user, rpc }) {
        const allowedBranches = session.user_branches?.allowed_branches || {};
        let currentBranchId = session.user_branches?.current_branch || false;

        if (currentBranchId && !(currentBranchId in allowedBranches)) {
            currentBranchId = Object.keys(allowedBranches).map(Number)[0] || false;
        }

        const updateContext = () => {
            const allowedBranchIds = Object.keys(allowedBranches).map(Number);
            user.updateContext({
                allowed_branch_ids: allowedBranchIds,
                hospital_branch_id: currentBranchId || false,
            });
        };
        updateContext();

        return {
            get allowedBranches() {
                return allowedBranches;
            },
            get currentBranchId() {
                return currentBranchId;
            },
            get currentBranch() {
                return currentBranchId ? allowedBranches[currentBranchId] : null;
            },
            async setBranch(branchId) {
                const branchKey = String(branchId);
                if (!(branchKey in allowedBranches)) {
                    return;
                }
                await rpc("/smart_hospital/switch_branch", { branch_id: branchId });
                browser.setTimeout(() => browser.location.reload(), 50);
            },
        };
    },
};

registry.category("services").add("hospital_branch", branchService);
