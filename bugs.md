# 🐞 Known Issues & Bugs

This document lists the currently identified bugs and inconsistencies in the system related to user roles, account management, and profile updates.

---

## Role & Member Management Issues

1. **Invitation Role Persistence**
   - When a user is invited to a role but **does not have an account**, they can create one and join with that role successfully.
   - However, if the same user is **removed** and then **re-invited** with a **different role**, their role **does not update** to the new one.
   - Some bugs in invitation just like above one.

2. **Stale Role Display**
   - If a member is **removed** from one role and **invited** to another, the **previous role** still appears in the UI or database.

---

## Profile Management Issues

4. **Profile Update Failure**
   - User profiles **cannot be updated**; changes are not reflected even though requests are successful.

5. **Avatar Update Failure**
   - When a new user uploads or updates their avatar, the API responds successfully but the **avatar does not update** in the system.

---

## Account Management Issues

6. **Deactivate Account Not Working**
   - The **deactivate account** feature does not function; users remain active even after attempting deactivation.

---