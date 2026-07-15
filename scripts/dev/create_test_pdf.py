from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch

# Create a simple PDF with multiple pages
c = canvas.Canvas("test_lease.pdf", pagesize=letter)
width, height = letter

c.drawString(1*inch, height - 1*inch, "Lease Agreement")
c.drawString(1*inch, height - 1.5*inch, "This is a sample lease agreement for testing.")
c.drawString(1*inch, height - 2*inch, "Tenant: John Doe")
c.drawString(1*inch, height - 2.5*inch, "Landlord: Jane Smith")
c.showPage()

c.drawString(1*inch, height - 1*inch, "Monthly Rent: $1,500")
c.drawString(1*inch, height - 1.5*inch, "Lease Term: 12 months")
c.drawString(1*inch, height - 2*inch, "Security Deposit: $3,000")
c.showPage()

c.drawString(1*inch, height - 1*inch, "Additional Terms:")
c.drawString(1*inch, height - 1.5*inch, "1. No pets allowed")
c.drawString(1*inch, height - 2*inch, "2. Utilities included")
c.drawString(1*inch, height - 2.5*inch, "3. Parking space included")
c.showPage()

c.save()
print("Created test_lease.pdf with 3 pages")