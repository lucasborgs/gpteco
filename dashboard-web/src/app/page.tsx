import LandingHeader from '@/components/landing/LandingHeader'
import HeroSection from '@/components/landing/HeroSection'
import AboutSection from '@/components/landing/AboutSection'
import HowItWorksSection from '@/components/landing/HowItWorksSection'
import BenefitsSection from '@/components/landing/BenefitsSection'
import PricingSection from '@/components/landing/PricingSection'
import ContactSection from '@/components/landing/ContactSection'
import LandingFooter from '@/components/landing/LandingFooter'

export default function Home() {
  return (
    <>
      <LandingHeader />
      <main>
        <HeroSection />
        <AboutSection />
        <HowItWorksSection />
        <BenefitsSection />
        <PricingSection />
        <ContactSection />
      </main>
      <LandingFooter />
    </>
  )
}
