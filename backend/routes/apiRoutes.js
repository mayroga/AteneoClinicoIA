const express = require('express');
const router = express.Router();
const volunteerController = require('../controllers/volunteerController');
const professionalController = require('../controllers/professionalController');

// Rutas voluntarios
router.post('/volunteer/waiver', async (req, res) => {
    const { email } = req.body;
    const result = await volunteerController.acceptWaiver(email);
    res.json(result);
});

router.post('/volunteer/case', async (req, res) => {
    const { email, historyText, imageFile } = req.body;
    const result = await volunteerController.submitVolunteerCase(email, historyText, imageFile);
    res.json(result);
});

router.get('/volunteer/report/:email', async (req, res) => {
    const { email } = req.params;
    const report = await volunteerController.getVolunteerReport(email);
    res.json(report);
});

router.post('/volunteer/payment', async (req, res) => {
    const { email, amount } = req.body;
    const clientSecret = await volunteerController.createVolunteerPaymentIntent(email, amount);
    res.json({ client_secret: clientSecret });
});

// Rutas profesionales
router.post('/professional/waiver', async (req, res) => {
    const { email } = req.body;
    const result = await professionalController.acceptWaiver(email);
    res.json(result);
});

router.post('/professional/case', async (req, res) => {
    const { email, historyText, imageFile } = req.body;
    const result = await professionalController.submitProfessionalCase(email, historyText, imageFile);
    res.json(result);
});

router.get('/professional/report/:email', async (req, res) => {
    const { email } = req.params;
    const report = await professionalController.getProfessionalReport(email);
    res.json(report);
});

router.post('/professional/payment', async (req, res) => {
    const { email, amount } = req.body;
    const clientSecret = await professionalController.createProfessionalPaymentIntent(email, amount);
    res.json({ client_secret: clientSecret });
});

module.exports = router;
