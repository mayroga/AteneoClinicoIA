import express from 'express';
import cors from 'cors';
import bodyParser from 'body-parser';
import apiRoutes from './routes/apiRoutes.js';
import Stripe from 'stripe';

// Variables secretas desde Render
const {
  STRIPE_SECRET_KEY,
  STRIPE_WEBHOOK_SECRET,
  DATABASE_URL,
  EMAIL_API_KEY,
  SENDER_EMAIL,
  ADMIN_BYPASS_KEY,
  GEMINI_API_KEY,
  __firebase_config__
} = process.env;

const stripe = new Stripe(STRIPE_SECRET_KEY);

const app = express();

// Middlewares
app.use(cors());
app.use(bodyParser.json());
app.use(bodyParser.urlencoded({ extended: true }));

// Rutas
app.use('/api/v1', apiRoutes);

// Webhook de Stripe
app.post('/webhook', express.raw({ type: 'application/json' }), (req, res) => {
    const sig = req.headers['stripe-signature'];

    let event;

    try {
        event = stripe.webhooks.constructEvent(req.body, sig, STRIPE_WEBHOOK_SECRET);
    } catch (err) {
        console.error('Error en webhook de Stripe:', err.message);
        return res.status(400).send(`Webhook Error: ${err.message}`);
    }

    // Manejar eventos relevantes
    switch (event.type) {
        case 'payment_intent.succeeded':
            const paymentIntent = event.data.object;
            console.log(`Pago recibido: ${paymentIntent.id}`);
            // Aquí se podría actualizar la base de datos con el pago real
            break;
        case 'checkout.session.completed':
            const session = event.data.object;
            console.log(`Checkout completado: ${session.id}`);
            // Aquí se procesa el pago final y se asignan créditos reales
            break;
        default:
            console.log(`Evento no manejado: ${event.type}`);
    }

    res.json({ received: true });
});

// Inicio del servidor
const PORT = process.env.PORT || 8000;
app.listen(PORT, () => {
    console.log(`Servidor corriendo en puerto ${PORT}`);
});
