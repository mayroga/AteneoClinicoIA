const express = require('express');
const router = express.Router();
const { verifyAdminBypass, getProfessionalProfile, registerProfessional, getCase, submitDebate } = require('../controllers/professionalController');

// Registrar profesional
router.post('/register', async (req, res) => {
    try {
        const { email, name, specialty } = req.body;
        const profile = await registerProfessional(email, name, specialty);
        res.json({ profile });
    } catch (err) {
        res.status(400).json({ detail: err.message });
    }
});

// Obtener perfil profesional
router.get('/profile', async (req, res) => {
    try {
        const email = req.headers['email'];
        const profile = await getProfessionalProfile(email);
        res.json({ profile });
    } catch (err) {
        res.status(400).json({ detail: err.message });
    }
});

// Obtener nuevo caso
router.get('/get-case', async (req, res) => {
    try {
        const email = req.headers['email'];
        const c = await getCase(email);
        res.json({ case: c });
    } catch (err) {
        res.status(400).json({ detail: err.message });
    }
});

// Enviar debate profesional
router.post('/submit-debate', async (req, res) => {
    try {
        const email = req.headers['email'];
        const { case_id, professional_diagnosis, outcome } = req.body;
        const result = await submitDebate(email, case_id, professional_diagnosis, outcome);
        res.json(result);
    } catch (err) {
        res.status(400).json({ detail: err.message });
    }
});

module.exports = router;
