const { v4: uuidv4 } = require('uuid');
const db = require('../utils/database');
const STRIPE_SECRET_KEY = process.env.STRIPE_SECRET_KEY;
const stripe = require('stripe')(STRIPE_SECRET_KEY);

// Aceptar waiver
async function acceptWaiver(email, user_type) {
    await db.insertWaiver({ email, user_type, accepted_at: new Date() });
    return { email, user_type };
}

// Procesar pago del voluntario
async function processVolunteerPayment(email, amount) {
    const paymentIntent = await stripe.paymentIntents.create({
        amount: amount * 100, // en centavos
        currency: 'usd',
        receipt_email: email,
        metadata: { user_email: email, type: 'volunteer' }
    });
    return paymentIntent.client_secret;
}

// Subir caso de voluntario
async function submitCase(email, historyText, imageFile) {
    const caseId = uuidv4();
    const caseRecord = {
        case_id: caseId,
        volunteer_email: email,
        chief_complaint: historyText.split('\n')[0] || '',
        history_summary: historyText,
        image_url: `/uploads/${imageFile.filename}`,
        ai_hypothesis: 'Pendiente generación IA',
        differential_diagnoses: [],
        diagnostic_plan: '',
        created_at: new Date()
    };
    await db.insertVolunteerCase(caseRecord);

    // Generar mensaje viral para redes
    const socialMessage = `Un nuevo caso clínico ha sido subido por un voluntario. Caso ID: ${caseId}. Participa en el debate profesional.`;

    return { case_id: caseId, social_message: socialMessage, warning: 'Recuerda que la IA es para fines educativos y de debate clínico.' };
}

// Obtener reporte del voluntario
async function getVolunteerReport(email) {
    const report = await db.getLatestVolunteerCaseByEmail(email);
    if (!report) throw new Error('No se encontró reporte');
    return report;
}

module.exports = {
    acceptWaiver,
    processVolunteerPayment,
    submitCase,
    getVolunteerReport
};
