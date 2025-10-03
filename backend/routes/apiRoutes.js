import express from 'express';
import { createProfessionalPayment } from '../controllers/professionalController.js';
import { createVolunteerPayment } from '../controllers/volunteerController.js';

const router = express.Router();

// Endpoint para pago de profesionales de salud
router.post('/payment/professional', createProfessionalPayment);

// Endpoint para pago de voluntarios
router.post('/payment/volunteer', createVolunteerPayment);

export default router;
