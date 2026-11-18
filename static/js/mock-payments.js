const paymentChoice = document.getElementById("payment-method");
const newCard = document.getElementById("new-mock-card");
function updatePaymentFields() {
    const useNew = paymentChoice.value === "new";
    newCard.hidden = !useNew;
    newCard.disabled = !useNew;
}
paymentChoice.addEventListener("change", updatePaymentFields);
updatePaymentFields();
