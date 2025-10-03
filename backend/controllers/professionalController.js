import Stripe from 'stripe';
import { v4 as uuidv4 } from 'uuid';
import { getProfessionalByEmail, createProfessional, updateCredits, getCaseForProfessional, submitDebateResult } from '../models/professionalModel.js';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY);

// Registrar profesional
export const registerProfessional = async (req, res) => {
    try {
        const { email, name, specialty } = req.body;
        if (!email || !name || !specialty) {
            return res.status(400).json({ detail: 'Campos incompletos' });
        }

        let professional = await getProfessionalByEmail(email);
        if (!professional) {
            professional = await createProfessional({ email, name, specialty });
        }

        res.json({ profile: professional });
    } catch (error) {
        console.error('Error registerProfessional:', error);
        res.status(500).json({ detail: 'Error interno del servidor' });
    }
};

// Comprar créditos reales con Stripe
export const purchaseCredits = async (req, res) => {
    try {
        const { email, credits, price } = req.body;
        const professional = await getProfessionalByEmail(email);
        if (!professional) return res.status(404).json({ detail: 'Profesional no encontrado' });

        const session = await stripe.checkout.sessions.create({
            payment_method_types: ['card'],
            line_items: [
                {
                    price_data: {
                        currency: 'usd',
                        product_data: { name: `${credits} Créditos para Ateneo Clínico IA` },
                        unit_amount: price * 100,
                    },
                    quantity: 1,
                },
            ],
            mode: 'payment',
            success_url: `${process.env.FRONTEND_URL}/professional_flow?session_id={CHECKOUT_SESSION_ID}`,
            cancel_url: `${process.env.FRONTEND_URL}/professional_flow`,
            metadata: { email, credits }
        });

        res.json({ url: session.url });
    } catch (error) {
        console.error('Error purchaseCredits:', error);
        res.status(500).json({ detail: 'Error al crear sesión de pago' });
    }
};

// Obtener un caso para debate
export const getCase = async (req, res) => {
    try {
        const email = req.headers.email;
        const professional = await getProfessionalByEmail(email);
        if (!professional) return res.status(404).json({ detail: 'Profesional no encontrado' });
        if (professional.credits < 1) return res.status(403).json({ detail: 'No tienes créditos suficientes' });

        const caseData = await getCaseForProfessional(email);
        await updateCredits(email, -1); // descontar crédito
        res.json({ case: caseData });
    } catch (error) {
        console.error('Error getCase:', error);
        res.status(500).json({ detail: 'Error al obtener caso' });
    }
};

// Enviar refutación de un caso
export const submitDebate = async (req, res) => {
    try {
        const email = req.headers.email;
        const { case_id, professional_diagnosis, outcome } = req.body;

        const result = await submitDebateResult({ email, case_id, professional_diagnosis, outcome });

        res.json({ new_score: result.new_score, viral_message: result.viral_message });
    } catch (error) {
        console.error('Error submitDebate:', error);
        res.status(500).json({ detail: 'Error al enviar debate' });
    }
};
