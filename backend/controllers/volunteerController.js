import Stripe from 'stripe';
import { v4 as uuidv4 } from 'uuid';
import { getVolunteerByEmail, createVolunteer, updateCredits, getCaseForVolunteer, submitDebateResult } from '../models/volunteerModel.js';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY);

// Registrar voluntario
export const registerVolunteer = async (req, res) => {
    try {
        const { email, name } = req.body;
        if (!email || !name) {
            return res.status(400).json({ detail: 'Campos incompletos' });
        }

        let volunteer = await getVolunteerByEmail(email);
        if (!volunteer) {
            volunteer = await createVolunteer({ email, name });
        }

        res.json({ profile: volunteer });
    } catch (error) {
        console.error('Error registerVolunteer:', error);
        res.status(500).json({ detail: 'Error interno del servidor' });
    }
};

// Comprar créditos reales con Stripe ($40–$50)
export const purchaseCredits = async (req, res) => {
    try {
        const { email, credits, price } = req.body;
        const volunteer = await getVolunteerByEmail(email);
        if (!volunteer) return res.status(404).json({ detail: 'Voluntario no encontrado' });

        const session = await stripe.checkout.sessions.create({
            payment_method_types: ['card'],
            line_items: [
                {
                    price_data: {
                        currency: 'usd',
                        product_data: { name: `${credits} Créditos para Voluntario IA` },
                        unit_amount: price * 100,
                    },
                    quantity: 1,
                },
            ],
            mode: 'payment',
            success_url: `${process.env.FRONTEND_URL}/volunteer_flow?session_id={CHECKOUT_SESSION_ID}`,
            cancel_url: `${process.env.FRONTEND_URL}/volunteer_flow`,
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
        const volunteer = await getVolunteerByEmail(email);
        if (!volunteer) return res.status(404).json({ detail: 'Voluntario no encontrado' });
        if (volunteer.credits < 1) return res.status(403).json({ detail: 'No tienes créditos suficientes' });

        const caseData = await getCaseForVolunteer(email);
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
        const { case_id, volunteer_diagnosis, outcome } = req.body;

        const result = await submitDebateResult({ email, case_id, volunteer_diagnosis, outcome });

        res.json({ new_score: result.new_score, viral_message: result.viral_message });
    } catch (error) {
        console.error('Error submitDebate:', error);
        res.status(500).json({ detail: 'Error al enviar debate' });
    }
};
