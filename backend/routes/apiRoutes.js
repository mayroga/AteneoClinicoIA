import express from 'express';
import { registerVolunteer, purchaseCredits, getCase, submitDebate } from '../controllers/volunteerController.js';
import { registerProfessional, purchaseProfessionalCredits, getProfessionalCase, submitProfessionalDebate } from '../controllers/professionalController.js';

const router = express.Router();

// Rutas para Voluntarios
router.post('/volunteer/register', registerVolunteer);
router.post('/volunteer/purchase', purchaseCredits);
router.get('/volunteer/case', getCase);
router.post('/volunteer/debate', submitDebate);

// Rutas para Profesionales de Salud
router.post('/professional/register', registerProfessional);
router.post('/professional/purchase', purchaseProfessionalCredits);
router.get('/professional/case', getProfessionalCase);
router.post('/professional/debate', submitProfessionalDebate);

export default router;
