const { v4: uuidv4 } = require('uuid');
const db = require('../utils/database');
const STRIPE_SECRET_KEY = process.env.STRIPE_SECRET_KEY;
const stripe = require('stripe')(STRIPE_SECRET_KEY);
const ADMIN_BYPASS_KEY = process.env.ADMIN_BYPASS_KEY;

// Registrar profesional
async function registerProfessional(email, name, specialty) {
    let existing = await db.getProfessionalByEmail(email);
    if (existing) throw new Error('Profesional ya registrado');

    const profile = {
        email,
        name,
        specialty,
        credits: 1,
        score_refutation: 0
    };
    await db.insertProfessional(profile);
    return profile;
}

// Obtener perfil
async function getProfessionalProfile(email) {
    const profile = await db.getProfessionalByEmail(email);
    if (!profile) throw new Error('Perfil no encontrado');
    return profile;
}

// Obtener nuevo caso
async function getCase(email) {
    const profile = await db.getProfessionalByEmail(email);
    if (!profile) throw new Error('Perfil no encontrado');
    if (profile.credits < 1) throw new Error('No tienes créditos suficientes');

    const caseItem = await db.getRandomVolunteerCase();
    await db.decrementProfessionalCredit(email);
    return caseItem;
}

// Enviar debate profesional
async function submitDebate(email, case_id, professional_diagnosis, outcome) {
    const profile = await db.getProfessionalByEmail(email);
    if (!profile) throw new Error('Perfil no encontrado');

    let scoreChange = 0;
    if (outcome === 'victory') scoreChange = 10;
    else if (outcome === 'defeat') scoreChange = -5;

    const newScore = profile.score_refutation + scoreChange;
    await db.updateProfessionalScore(email, newScore);

    const viralMessage = `El Dr/a ${profile.name} participó en el debate del Caso ID ${case_id} y obtuvo ${scoreChange >= 0 ? '+' : ''}${scoreChange} puntos en su Refutation Score. ¡Únete al debate!`;

    return { new_score: newScore, viral_message: viralMessage };
}

module.exports = {
    registerProfessional,
    getProfessionalProfile,
    getCase,
    submitDebate,
    verifyAdminBypass: (key) => key === ADMIN_BYPASS_KEY
};
