import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useNavigate } from "react-router-dom";
import { useToast } from "@/hooks/use-toast";
import { Loader2, ArrowLeft, Download } from "lucide-react";

interface ExtractFormData {
  email: string;
  password: string;
  postUrl: string;
}

const Extract = () => {
  const [formData, setFormData] = useState<ExtractFormData>({
    email: "",
    password: "",
    postUrl: ""
  });
  const [isLoading, setIsLoading] = useState(false);
  const [emails, setEmails] = useState<string[]>([]);
  const navigate = useNavigate();
  const { toast } = useToast();

  const handleInputChange = (field: keyof ExtractFormData) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData(prev => ({
      ...prev,
      [field]: e.target.value
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      const response = await fetch('https://scrnk-io.onrender.com/extract/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email: formData.email,
          password: formData.password,
          post_url: formData.postUrl
        }),
      });

      if (!response.ok) throw new Error('Failed to extract emails');

      const result = await response.json();
      setEmails(result.emails || []);
      
      navigate('/results', { 
        state: { 
          emails: result.emails || [],
          postUrl: formData.postUrl,
          status: 'success'
        }
      });
    } catch (error) {
      console.error('Extraction error:', error);
      toast({
        title: "Extraction Failed",
        description: "Unable to extract emails. Please check your connection and try again.",
        variant: "destructive",
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleDownload = async (format: "csv" | "txt") => {
    try {
      const response = await fetch(`http://127.0.0.1:8000/download/?format=${format}`);
      if (!response.ok) throw new Error("Download failed");

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", format === "csv" ? "emails.csv" : "emails.txt");
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (error) {
      console.error("Download error:", error);
      toast({
        title: "Download Failed",
        description: "Could not download emails. Try again.",
        variant: "destructive",
      });
    }
  };

  const isFormValid = formData.email && formData.password && formData.postUrl;

  return (
    <div className="min-h-screen bg-background py-16">
      <div className="container mx-auto px-4 max-w-2xl">
        <div className="mb-8">
          <Button
            variant="ghost"
            onClick={() => navigate('/')}
            className="font-kode mb-4 text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back to Home
          </Button>
          <h1 className="font-bungee text-4xl text-primary mb-2">
            Extract Emails
          </h1>
          <p className="font-kode text-muted-foreground">
            Fill in your details to start extracting emails from the post URL
          </p>
        </div>

        <Card className="shadow-lg border-border">
          <CardHeader>
            <CardTitle className="font-rampart text-xl text-card-foreground">
              Extraction Details
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-6">
              <div className="space-y-2">
                <Label>Email Address</Label>
                <Input
                  id="email"
                  type="email"
                  value={formData.email}
                  onChange={handleInputChange('email')}
                  placeholder="your.email@example.com"
                  required
                  disabled={isLoading}
                />
              </div>

              <div className="space-y-2">
                <Label>Password</Label>
                <Input
                  id="password"
                  type="password"
                  value={formData.password}
                  onChange={handleInputChange('password')}
                  placeholder="••••••••"
                  required
                  disabled={isLoading}
                />
              </div>

              <div className="space-y-2">
                <Label>Post URL</Label>
                <Input
                  id="postUrl"
                  type="url"
                  value={formData.postUrl}
                  onChange={handleInputChange('postUrl')}
                  placeholder="https://example.com/post/123"
                  required
                  disabled={isLoading}
                />
              </div>

              <Button
                type="submit"
                className="w-full font-rampart text-lg py-6 bg-primary hover:bg-primary/90 text-primary-foreground"
                disabled={!isFormValid || isLoading}
              >
                {isLoading ? (
                  <>
                    <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                    Extracting... please wait
                  </>
                ) : (
                  'Extract Emails'
                )}
              </Button>
            </form>

            {emails.length > 0 && (
              <div className="mt-6 flex gap-4">
                <Button onClick={() => handleDownload("csv")} className="flex-1">
                  <Download className="w-4 h-4 mr-2" /> Download CSV
                </Button>
                <Button onClick={() => handleDownload("txt")} className="flex-1">
                  <Download className="w-4 h-4 mr-2" /> Download TXT
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default Extract;
