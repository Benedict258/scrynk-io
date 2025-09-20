import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Mail, Link, Zap } from "lucide-react";
import { useNavigate } from "react-router-dom";

const Landing = () => {
  const navigate = useNavigate();

  const steps = [
    {
      icon: Mail,
      title: "Enter Credentials",
      description: "Provide your email and password for secure access"
    },
    {
      icon: Link,
      title: "Paste Post URL",
      description: "Add the URL of the post you want to extract emails from"
    },
    {
      icon: Zap,
      title: "Get Results",
      description: "Extract emails instantly and view results in seconds"
    }
  ];

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 py-16 max-w-6xl">
        {/* Header */}
        <div className="text-center mb-16">
          <h1 className="font-bungee text-6xl md:text-8xl text-primary mb-6">
            Scrynk.io
          </h1>
          <p className="font-kode text-xl text-foreground mb-4">
            Extract Emails Smarter
          </p>
          <p className="font-rampart text-lg text-muted-foreground max-w-2xl mx-auto">
            Paste a post URL, log in, and fetch emails in seconds. Simple, fast, and efficient email extraction.
          </p>
        </div>

        {/* Steps */}
        <div className="grid md:grid-cols-3 gap-8 mb-16">
          {steps.map((step, index) => (
            <Card key={index} className="p-8 text-center hover:shadow-lg transition-shadow border-border">
              <div className="w-16 h-16 bg-primary/10 rounded-full flex items-center justify-center mx-auto mb-6">
                <step.icon className="w-8 h-8 text-primary" />
              </div>
              <h3 className="font-rampart text-xl mb-4 text-card-foreground">
                {index + 1}. {step.title}
              </h3>
              <p className="font-kode text-sm text-muted-foreground leading-relaxed">
                {step.description}
              </p>
            </Card>
          ))}
        </div>

        {/* CTA */}
        <div className="text-center">
          <Button 
            size="lg" 
            className="font-rampart text-lg px-12 py-6 bg-primary hover:bg-primary/90 text-primary-foreground"
            onClick={() => navigate('/extract')}
          >
            Get Started
          </Button>
        </div>
      </div>
    </div>
  );
};

export default Landing;