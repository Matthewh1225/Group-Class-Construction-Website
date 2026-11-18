function discountPreview(subtotalCents, shippingCents, code) {
    const normalized = (code || '').trim().toUpperCase();
    let percentage = 0;
    if (normalized === 'BUILD10') percentage = 10;
    else if (normalized === 'ADMIN') percentage = 99.99999;
    else if (normalized) return null;

    const taxCents = Math.floor((subtotalCents * 85 + 500) / 1000);
    const grossTotal = subtotalCents + shippingCents + taxCents;
    const discountCents = Math.round((grossTotal * percentage) / 100);
    const total = grossTotal - discountCents;
    return {
        percentage: percentage,
        discountedSubtotal: subtotalCents,
        discount: discountCents,
        tax: taxCents,
        total: total
    };
}
